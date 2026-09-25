from __future__ import annotations
import json, zipfile
from pathlib import Path
from .signing import bundle_digest, sign_manifest


def build(source_dir: str|Path, output: str|Path, *, app_id: str, version: str, kind: str, entrypoint: str,
          signer: str, secret: str, supported_modes: list[str], capabilities: list[str] | None=None, limits: dict|None=None):
    source_dir=Path(source_dir); output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    manifest={"schema_version":"1","app_id":app_id,"version":version,"kind":kind,"entrypoint":entrypoint,"capabilities":capabilities or [],"supported_modes":supported_modes,"signer":signer,"signature":"","digest":"","limits":limits or {}}
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED) as z:
        for p in sorted(source_dir.rglob("*")):
            if p.is_file(): z.write(p,p.relative_to(source_dir).as_posix())
    manifest["digest"]=bundle_digest(output)
    manifest["signature"]=sign_manifest(manifest,secret)
    with zipfile.ZipFile(output,"a",zipfile.ZIP_DEFLATED) as z: z.writestr("manifest.json",json.dumps(manifest,indent=2,sort_keys=True))
    return output
