# InfluenceMapper-Service

The services are:
- web: The web server that serves the InfluenceMapper web application.
- core: The core service that wraps the API calls to the InfluenceMapper API.
- broker_study: The broker service that passes study-entity messages from the web and cores services.
- broker_author: The broker service that passes author-entity messages from the web and cores services.

To start all services, run the following command:
```bash
docker-compose up
```