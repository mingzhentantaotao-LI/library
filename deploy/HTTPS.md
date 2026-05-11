# HTTPS and Domain Setup

This server can serve the Web UI on a public IP, but a trusted HTTPS certificate needs a real domain name that resolves to the server. Let's Encrypt will not issue a normal browser-trusted certificate for the bare IP address.

## DNS requirement

Create an `A` record:

```text
kb.example.com -> 175.178.175.57
```

Wait until the server resolves the domain:

```bash
dig +short kb.example.com
```

## Recommended server layout

Run the Python app only on localhost:

```ini
KB_HOST=127.0.0.1
KB_PORT=8080
```

Let nginx own public `80` and `443`, then reverse proxy to `127.0.0.1:8080`.

## Nginx site template

Replace `kb.example.com` with the real domain.

```nginx
server {
    listen 80;
    server_name kb.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Install and enable:

```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo install -m 0644 deploy/nginx-personal-kb.conf /etc/nginx/sites-available/personal-kb
sudo ln -sf /etc/nginx/sites-available/personal-kb /etc/nginx/sites-enabled/personal-kb
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d kb.example.com
```

After the certificate is issued, visit:

```text
https://kb.example.com/
```
