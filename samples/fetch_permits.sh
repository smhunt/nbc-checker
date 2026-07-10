#!/bin/bash
# Fetch publicly published sample/example building-permit drawing sets for
# extraction testing. All are government/public-agency publications posted as
# examples or public records. They are NOT redistributed in this repo
# (samples/external/ is gitignored): the Calgary sets state reproduction
# without permission is prohibited, and most others carry no explicit license.
# Sources verified 2026-07-10 (see progress.md session 5c).
set -uo pipefail
cd "$(dirname "$0")/external" 2>/dev/null || { mkdir -p "$(dirname "$0")/external"; cd "$(dirname "$0")/external"; }
mkdir -p permits && cd permits

get() { # get <output-name> <url>
  if [ -s "$1" ]; then echo "have   $1"; else
    curl -fsSL -A "Mozilla/5.0 (permit-sample-fetch for code-compliance research)" -o "$1" "$2" \
      && echo "fetched $1" || echo "FAILED  $1"
  fi
}

# --- Canadian (NBC / NBC(AE) / OBC jurisdictions) --------------------------
get calgary_new_home_dp_bp_23sheets.pdf "https://www.calgary.ca/content/dam/www/pda/pd/documents/carls/sample-drawings/DP-BP-new-home-sample-drawings.pdf"
get calgary_secondary_suite_new.pdf     "https://www.calgary.ca/content/dam/www/pda/pd/documents/pdf/sample-permit-drawings/Sample-Adding-Secondary-Suite-drawings.pdf"
get calgary_secondary_suite_legalize.pdf "https://www.calgary.ca/content/dam/www/pda/pd/documents/pdf/sample-permit-drawings/Sample-Legalize-Existing-Secondary-Suite-Drawings.pdf"
get calgary_basement_development.pdf    "https://www.calgary.ca/content/dam/www/pda/pd/documents/pdf/sample-permit-drawings/Sample-Basement-Drawings.pdf"
get calgary_garage.pdf                  "https://www.calgary.ca/content/dam/www/pda/pd/documents/pdf/sample-permit-drawings/Sample-Garage-Drawings.pdf"
get calgary_patio.pdf                   "https://www.calgary.ca/content/dam/www/pda/pd/documents/carls/development-permit/sample-patio-drawings.pdf"
get ottawa_addition.pdf                 "https://documents.ottawa.ca/sites/documents/files/documents/addition_plan_en.pdf"
get ottawa_sundeck.pdf                  "https://documents.ottawa.ca/sites/documents/files/documents/sundeck_plan_en.pdf"
get ottawa_accessory_building.pdf       "https://documents.ottawa.ca/sites/documents/files/documents/accessory_building_en_1.pdf"
get ottawa_finished_basement.pdf        "https://documents.ottawa.ca/sites/documents/files/documents/bsmt_plan_en.pdf"
get edmonton_garage_guide.pdf           "https://www.edmonton.ca/sites/default/files/public-files/Detached_Garage_Design_Guide.pdf"
get alberta_garage_guide_ogl.pdf        "https://open.alberta.ca/dataset/099a3321-433e-4e83-b36e-84a4eb4875f9/resource/262d9c17-e377-49c7-aa69-ed7a8d6690b0/download/wlibrarystaffgovdocrepositorycurrent-dlpbuilding-a-detached-residential-garage.pdf"
get winnipeg_garages_accessory.pdf      "https://www.winnipeg.ca/media/5008"

# --- US (extraction-density + Part 3 exercise; code values differ) ----------
get cotati_adu_approved.pdf             "https://www.cotaticity.gov/DocumentCenter/View/2606/ADU---622-McGinnis-Cir-Approved-Plans"
get cotati_mixed_use_approved.pdf       "https://www.cotaticity.gov/DocumentCenter/View/2611/MIXED-USE---1818-La-Plaza-Approved-Plans"
get lynnwood_tenant_improvement.pdf     "https://www.lynnwoodwa.gov/files/sharedassets/public/v/1/dbs/guides/tenant-improvement-sample-drawings.pdf"
get sandiego_adu_plan_a_24x36.pdf       "https://www.sandiegocounty.gov/content/dam/sdc/pds/bldg/adu_info/pds670_24x36.pdf"
get trdi_small_commercial_cds.pdf       "http://trdi.org/wp-content/uploads/2024/03/3.-2024.02.29-Architectural-Construction-Drawing.pdf"

# Deliberately skipped (very large; fetch manually if needed):
#   Cotati SFD 145MB:        https://www.cotaticity.gov/DocumentCenter/View/2621/...
#   Cotati Townhome 610MB:   https://www.cotaticity.gov/DocumentCenter/View/2615/...
#   Cotati Multi-family 124MB: https://www.cotaticity.gov/DocumentCenter/View/2610/...
# Blocked to non-browser clients (403): Vancouver sample drawing packages.
# Matched IFC+PDF (NIBS Common BIM Files) offline as of 2026-07-10 — retry portal.nibs.org.

echo; echo "--- verification ---"
for f in *.pdf; do
  head -c4 "$f" | grep -q "%PDF" && echo "ok  $f ($(du -h "$f" | cut -f1))" || echo "BAD $f (not a PDF)"
done
