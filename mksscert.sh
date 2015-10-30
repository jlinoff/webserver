#!/bin/bash
#
# Make a self signed certificate for the local host.
#
#    Key  Attribute
#    ===  ====================  =================================================
#    C    countryName           ISO 3166 country code (2 characters).
#    CN   commonName            Common name, in this case the hostname.
#    L    localityName          Locality (city).
#    O    organizationName      Organization name (e.g. company name).
#    OU   organizationUnitName  Organization unit name (e.g. security division)
#    ST   stateOrProvinceName   Full name of state or province.
#
echo "INFO: Creating the self-signed certificate."
[ -d certs ] && rm -rf certs
mkdir certs
openssl req \
  -subj '/CN=localhost/O=My Organization LTD/C=US/ST=Washington/L=Seattle' \
  -new \
  -newkey rsa:2048 \
  -days 365 \
  -nodes \
  -x509 \
  -sha256 \
  -keyout certs/webserver.key \
  -out certs/webserver.crt
cat certs/webserver.crt certs/webserver.key >certs/webserver.pem
echo "INFO: Created certs/webserver.pem."

