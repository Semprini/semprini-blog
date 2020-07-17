# Blogging system for [semprini.ml](https://semprini.ml)

# Boilerplate for nginx, docker and postgres with Let's Encrypt on docker-compose

`init-letsencrypt.sh` fetches and ensures the renewal of a Let’s
Encrypt certificate for one or multiple domains in a docker-compose
setup with nginx.

## Installation
1. [Install docker-compose](https://docs.docker.com/compose/install/#install-compose).

2. Clone this repository: `git clone https://github.com/wmnnd/nginx-certbot.git .`

3. Modify configuration:
- Add domains and email addresses to init-letsencrypt.sh
- Replace all occurrences of example.org with primary domain (the first one you added to init-letsencrypt.sh) in data/nginx/app.conf

4. Run the init script:

        ./init-letsencrypt.sh

5. Run the server:

        docker-compose up

