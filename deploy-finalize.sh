#!/bin/sh

sudo systemctl restart httpd-ssl
echo RIKSTERMBANKEN_WEB_VERSION=\"$(/usr/bin/git describe)\" > rb_version.py
