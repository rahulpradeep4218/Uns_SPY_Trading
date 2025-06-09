#!/bin/sh

#create required directories
mkdir -p /var/www/certbot

#Generate initial certificates if missing
if [ ! -f /etc/letsencrypt/live/rahulpradeep.com/fullchain.pem ]; then
    echo "Generating initial SSL certificates..."

    # start temporary http only nginx
    cp /default-temp.conf /etc/nginx/conf.d/default.conf
    nginx -g "daemon on;"

    # Request certificates (using standalone mode since we are not using --nginx plugin)
    certbot certonly --webroot --non-interactive --agree-tos \
        --email rahulpradeep4218@gmail.com \
        -d rahulpradeep.com -d www.rahulpradeep.com \
        -w /var/www/certbot

    #stop temporary nginx
    nginx -s stop
    #Restore original config
    cp /default.conf /etc/nginx/conf.d/default.conf
fi

# Start renewal loop in background
while :; do
    echo "Renewing SSL certificates..."
    certbot renew --quiet --no-random-sleep-on-renew
    sleep 12h
done &
cp /default.conf /etc/nginx/conf.d/default.conf
# Start production nginx with SSL
exec nginx -g "daemon off;"