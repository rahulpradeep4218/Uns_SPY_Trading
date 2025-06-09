#!/bin/sh

nginx -s stop 2>/dev/null || true


# Request initial certificates (only if not already present)
if [ ! -f "/etc/letsencrypt/live/rahulpradeep.com/fullchain.pem" ]; then

    certbot certonly --nginx --non-interactive --agree-tos \
        --email rahulpradeep4218@gmail.com \
        -d rahulpradeep.com -d www.rahulpradeep.com
fi

# Renew certificates every 12 hours (Let`s Encrypt caches for 24h)
while :; do
    certbot renew --quiet --pre-hook "nginx -s stop" --post-hook "nginx -g 'daemon off;' &"
    sleep 12h # Sleep for 12 hours
done &

#Start Nginx
nginx -g "daemon off;"