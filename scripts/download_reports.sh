#!/bin/bash
# Downloads Tata Steel Integrated Reports & Annual Accounts (FY2022-23 to FY2025-26)
# from the official tatasteel.com investor relations pages into data/raw/
set -e
mkdir -p data/raw
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
curl -L -A "$UA" -o data/raw/TataSteel_FY2022-23.pdf https://www.tatasteel.com/media/18370/tata-steel-ir-2022-23.pdf
curl -L -A "$UA" -o data/raw/TataSteel_FY2023-24.pdf https://www.tatasteel.com/media/21244/integrated-report-and-annual-accounts-fy2023-24.pdf
curl -L -A "$UA" -o data/raw/TataSteel_FY2024-25.pdf https://www.tatasteel.com/media/23973/fy25-integratedreport.pdf
curl -L -A "$UA" -o data/raw/TataSteel_FY2025-26.pdf https://www.tatasteel.com/media/25904/tatasteel-iar-2025-26.pdf
echo "All four reports downloaded to data/raw/"
