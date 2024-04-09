#!/bin/sh

cd /var/www/rikstermbanken/bankvalvet
git pull
python3 /var/www/rikstermbanken/src/import_bankvalvet.py /var/www/rikstermbanken/bankvalvet
