"""Sun-Panel OpenAPI v1 client and CLI. Python 3.11+, no dependencies."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import ssl
import sys
from typing import Any
import urllib.error
import urllib.parse
import urllib.request


class PanelError(Exception):
    def __init__(self, message: str, code: int | str = "CLIENT_ERROR"):
        super().__init__(message)
        self.code = code


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPERATIONS = {
    "version": ("version", False),
    "groups": ("itemGroup/getList", False),
    "group": ("itemGroup/getInfo", False),
    "item": ("item/getInfoByOnlyName", False),
    "create": ("item/create", True),
    "update": ("item/update", True),
}
STR_FIELDS = {"onlyName", "title", "url", "lanUrl", "iconUrl", "description", "itemGroupOnlyName"}
ITEM_FIELDS = STR_FIELDS | {"itemGroupID", "isSaveIcon"}


def normalize_base(value: str, allow_http: bool = False) -> str:
    u = urllib.parse.urlsplit(value.strip())
    if not u.hostname or u.username or u.password or u.query or u.fragment:
        raise PanelError("Base URL must contain only scheme, host, port and optional /openapi/v1.")
    if u.scheme != "https" and not (u.scheme == "http" and allow_http):
        raise PanelError("HTTPS required. For an explicitly approved LAN HTTP URL set SUN_PANEL_ALLOW_HTTP=1.")
    path = u.path.rstrip("/")
    if path not in ("", "/openapi/v1"):
        raise PanelError("Base URL path must be empty or /openapi/v1.")
    return urllib.parse.urlunsplit((u.scheme, u.netloc, "/openapi/v1", "", ""))


class PanelClient:
    def __init__(self, base_url: str, token: str, *, allow_http: bool = False,
                 allow_write: bool = False, timeout: float = 20):
        self.base_url = normalize_base(base_url, allow_http)
        self.token = token.strip()
        if not self.token or any(c in self.token for c in "\r\n"):
            raise PanelError("Set SUN_PANEL_TOKEN to a nonempty OpenAPI token; do not put it in command arguments.")
        self.allow_write = allow_write
        self.timeout = timeout
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    @classmethod
    def from_env(cls, *, allow_write: bool = False) -> PanelClient:
        base = os.environ.get("SUN_PANEL_BASE_URL", "")
        if not base:
            raise PanelError("Set SUN_PANEL_BASE_URL to your Sun-Panel URL.")
        return cls(base, os.environ.get("SUN_PANEL_TOKEN", ""),
                   allow_http=os.environ.get("SUN_PANEL_ALLOW_HTTP") == "1",
                   allow_write=allow_write)

    def scrub(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return obj.replace(self.token, "[REDACTED]")
        if isinstance(obj, list):
            return [self.scrub(x) for x in obj]
        if isinstance(obj, dict):
            return {k: self.scrub(v) for k, v in obj.items()}
        return obj

    def request(self, operation: str, payload: dict | None = None) -> dict:
        if operation not in OPERATIONS:
            raise PanelError("Unsupported operation; raw endpoint calls are not exposed.")
        path, mutates = OPERATIONS[operation]
        if mutates and not self.allow_write:
            raise PanelError("Write access is disabled.", "READ_ONLY")
        req = urllib.request.Request(self.base_url + "/" + path,
            data=json.dumps(payload or {}, ensure_ascii=False).encode("utf-8"),
            method="POST", headers={"token": self.token, "Content-Type": "application/json",
                                    "Accept": "application/json"})
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read(2_000_001)
                content_type = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            if 300 <= status < 400:
                raise PanelError("Redirect refused; token was not forwarded. Check reverse-proxy authentication.", "REDIRECT") from None
            raise PanelError(f"HTTP {status}; check connectivity and authentication.", "HTTP_ERROR") from None
        except (OSError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", exc)
            detail = type(reason).__name__
            if getattr(reason, "errno", None) is not None:
                detail += f" errno={reason.errno}"
            message = f"Network/TLS failure ({detail}); no automatic retry."
            if mutates:
                message += " Write outcome is unknown: read the target before retrying."
            raise PanelError(message, "NETWORK_ERROR") from None
        if len(raw) > 2_000_000:
            raise PanelError("Response exceeds 2 MB.", "INVALID_RESPONSE")
        if "json" not in content_type.lower():
            detail = "Lucky authentication intercepted the API request." if b"Lucky Auth" in raw else "Expected a JSON API response."
            raise PanelError(detail, "NON_JSON")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise PanelError("Invalid JSON API response.", "INVALID_RESPONSE") from None
        if not isinstance(data, dict) or type(data.get("code")) is not int:
            raise PanelError("Missing integer Sun-Panel business code.", "INVALID_RESPONSE")
        if data["code"] != 0:
            msg = str(self.scrub(str(data.get("msg", "API operation failed"))))[:240]
            raise PanelError(f"Sun-Panel code {data['code']}: {msg}", data["code"])
        return data

    def group(self, *, item_group_id: int | None = None, only_name: str | None = None) -> dict:
        if item_group_id is not None:
            if type(item_group_id) is not int or item_group_id <= 0:
                raise PanelError("Group ID must be a positive integer.")
            return self.request("group", {"itemGroupID": item_group_id})
        if not isinstance(only_name, str) or not only_name.strip():
            raise PanelError("Supply a group ID or a nonempty group onlyName.")
        return self.request("group", {"onlyName": only_name})

    def item(self, only_name: str) -> dict:
        if not isinstance(only_name, str) or not only_name.strip():
            raise PanelError("A nonempty item onlyName is required; title is not an identifier.")
        return self.request("item", {"onlyName": only_name})

    def validate_item(self, body: dict, *, create: bool) -> dict:
        if not isinstance(body, dict) or set(body) - ITEM_FIELDS:
            raise PanelError("Item must be an object containing only documented fields.")
        value = dict(body)
        for key in STR_FIELDS & value.keys():
            if not isinstance(value[key], str):
                raise PanelError(f"{key} must be a string; use an empty string to clear an optional field.")
        if not value.get("onlyName", "").strip():
            raise PanelError("onlyName is required for reliable lookup and verification.")
        if "itemGroupID" in value and (type(value["itemGroupID"]) is not int or value["itemGroupID"] <= 0):
            raise PanelError("itemGroupID must be a positive integer.")
        if "isSaveIcon" in value and type(value["isSaveIcon"]) is not bool:
            raise PanelError("isSaveIcon must be a boolean.")
        if "itemGroupID" in value and "itemGroupOnlyName" in value:
            raise PanelError("Supply only one group selector to avoid ambiguous moves.")
        if "itemGroupOnlyName" in value and not value["itemGroupOnlyName"].strip():
            raise PanelError("itemGroupOnlyName must not be blank; prefer a known group ID.")
        if create and not value.get("url"):
            raise PanelError("url is required when creating an item.")
        for key in ("url", "lanUrl", "iconUrl"):
            if value.get(key):
                u = urllib.parse.urlsplit(value[key])
                if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
                    raise PanelError(f"{key} must be an HTTP(S) URL without embedded credentials.")
        if not create and set(value) == {"onlyName"}:
            raise PanelError("No changes supplied.")
        return value

    def change_item(self, operation: str, body: dict, *, execute: bool = False) -> dict:
        if operation not in ("create", "update"):
            raise PanelError("Only create and update are supported.")
        if execute and not self.allow_write:
            raise PanelError("Write access is disabled.", "READ_ONLY")
        supplied = self.validate_item(body, create=operation == "create")
        if operation == "update":
            # 1.8.1 fixed omitted fields erasing existing icons. Earlier releases
            # cannot safely support sparse updates when icon read-back is empty.
            version_data = self.request("version").get("data")
            version = version_data.get("version", "") if isinstance(version_data, dict) else ""
            match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(version))
            if not match or tuple(map(int, match.groups())) < (1, 8, 1):
                raise PanelError("Updates require stable Sun-Panel 1.8.1 or newer to preserve omitted fields.", "UNSUPPORTED_VERSION")
        before = None
        try:
            found = self.item(supplied["onlyName"])
            if not isinstance(found.get("data"), dict):
                raise PanelError("Invalid item data; refusing write.", "INVALID_RESPONSE")
            before = found["data"]
        except PanelError as exc:
            if exc.code != 1203 or operation != "create":
                raise
        if operation == "create" and before is not None:
            raise PanelError("onlyName already exists; choose update or another identifier.", 1202)
        if "itemGroupID" in supplied:
            self.group(item_group_id=supplied["itemGroupID"])
        elif "itemGroupOnlyName" in supplied:
            self.group(only_name=supplied["itemGroupOnlyName"])
        # Do not echo omitted fields from getInfo: notably, iconUrl may be blank
        # in that response while a working icon remains visible in the UI.
        submitted = dict(supplied)
        if operation == "create":
            submitted.setdefault("isSaveIcon", False)
        result = {"operation": operation, "executed": False, "before": before,
                  "submitted": submitted}
        if not execute:
            return self.scrub(result)
        self.request(operation, submitted)
        result["executed"] = True
        try:
            after = self.item(supplied["onlyName"])["data"]
            result["after"] = after
            checked = {k: v for k, v in supplied.items() if k not in ("isSaveIcon", "iconUrl")}
            result["mismatches"] = [k for k, v in checked.items() if after.get(k) != v]
            result["verified_fields"] = [k for k, v in checked.items() if after.get(k) == v]
            result["unverified_fields"] = []
            if "iconUrl" in supplied:
                actual = after.get("iconUrl")
                if actual and actual == supplied["iconUrl"] and not supplied.get("isSaveIcon", False):
                    result["verified_fields"].append("iconUrl")
                elif actual and actual != supplied["iconUrl"] and not supplied.get("isSaveIcon", False):
                    result["mismatches"].append("iconUrl")
                else:
                    result["unverified_fields"].append("iconUrl")
                    result["verification_note"] = (
                        "The API accepted the write, but icon read-back is not authoritative. "
                        "Check the rendered card and image load before declaring success; do not repeat the write.")
            result["verified"] = not result["mismatches"] and not result["unverified_fields"]
            result["verification_status"] = ("mismatch" if result["mismatches"] else
                "needs_visual_check" if result["unverified_fields"] else "verified")
        except (PanelError, KeyError, AttributeError):
            result["verified"] = False
            result["verification_error"] = "Write was accepted but read-back failed; inspect before retrying."
        return self.scrub(result)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    sub.add_parser("groups")
    group = sub.add_parser("group")
    sel = group.add_mutually_exclusive_group(required=True)
    sel.add_argument("--id", type=int)
    sel.add_argument("--only-name")
    item = sub.add_parser("item")
    item.add_argument("--only-name", required=True)
    for command in ("create", "update"):
        write = sub.add_parser(command)
        write.add_argument("--file", required=True, help="UTF-8 JSON file of documented item fields")
        write.add_argument("--yes", action="store_true", help="Execute; default is a read-only preview")
    a = p.parse_args()
    try:
        client = PanelClient.from_env(allow_write=getattr(a, "yes", False))
        if a.command in ("version", "groups"):
            result = client.request(a.command)
        elif a.command == "group":
            result = client.group(item_group_id=a.id, only_name=a.only_name)
        elif a.command == "item":
            result = client.item(a.only_name)
        else:
            body = json.loads(Path(a.file).read_text(encoding="utf-8-sig"))
            result = client.change_item(a.command, body, execute=a.yes)
        print(json.dumps(client.scrub(result), ensure_ascii=False, indent=2))
        return 0 if result.get("verified", True) else 3
    except (PanelError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "code": getattr(exc, "code", "CLIENT_ERROR")}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
