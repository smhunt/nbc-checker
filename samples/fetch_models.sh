#!/usr/bin/env bash
# Fetch real open-data IFC house models for extractor testing (T2).
# Downloads land in samples/external/ (gitignored). Skips gracefully on 404
# so the script is safe to re-run and safe when upstream hosts move files.
#
# Sources:
#   - AC20-FZK-Haus.ifc          KIT / IFC Wiki open dataset — two-storey
#                                 detached house, IFC4, with stair + spaces.
#   - wall-with-opening-and-window.ifc
#                                 buildingSMART Sample-Test-Files — minimal
#                                 IFC4 wall + window (window attribute test).
#   - AC20-Institute-Var-2.ifc   KIT / IFC Wiki open dataset — larger
#                                 institute building, IFC4.
set -u

DIR="$(cd "$(dirname "$0")" && pwd)/external"
mkdir -p "$DIR"

fetch() {
    local url="$1" out="$2"
    if [ -s "$DIR/$out" ]; then
        echo "SKIP  $out (already present)"
        return 0
    fi
    echo "GET   $url"
    if curl -fL --connect-timeout 15 --retry 2 -o "$DIR/$out.part" "$url"; then
        mv "$DIR/$out.part" "$DIR/$out"
        echo "OK    $out ($(du -h "$DIR/$out" | cut -f1))"
    else
        rm -f "$DIR/$out.part"
        echo "FAIL  $out (download failed; skipping)"
    fi
}

# NOTE (2026-07-07): the originally planned URLs
#   .../images/b/b1/AC20-Institute-Var-2.ifc          -> 404 (wiki re-hashed to /9/98/)
#   .../raw/master/IFC%204.0/BuildingSMARTSpec/...    -> 404 (repo restructured; default
#                                                        branch is now `main`, file moved
#                                                        under "IFC 4.0.2.1 (IFC 4)/ISO
#                                                        Spec - ReferenceView_V1.2/")
# were corrected to the URLs below, verified against the live hosts.
fetch "https://www.ifcwiki.org/images/e/e3/AC20-FZK-Haus.ifc" "AC20-FZK-Haus.ifc"
fetch "https://github.com/buildingSMART/Sample-Test-Files/raw/main/IFC%204.0.2.1%20%28IFC%204%29/ISO%20Spec%20-%20ReferenceView_V1.2/wall-with-opening-and-window.ifc" "wall-with-opening-and-window.ifc"
fetch "https://www.ifcwiki.org/images/9/98/AC20-Institute-Var-2.ifc" "AC20-Institute-Var-2.ifc"

echo
echo "Downloaded models in $DIR:"
ls -lh "$DIR" | awk 'NR>1 {print "  " $9 "  " $5}'
