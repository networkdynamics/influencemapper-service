# InfluenceMapper Web Service

This is the InfluenceMapper web application. It provides access to the OpenAI service through the [InfluenceMapper library](https://github.com/networkdynamics/influencemapper). 

## Installation
The application is only available through docker and docker-compose. You have to first install docker in your system. Please visit the [official docker website](https://docs.docker.com/get-started/get-docker/) for instructions on how to install docker in your system. Once you have installed docker, you can start the project by first clone the repository and then running the following command:

```bash
docker-compose up
```

## Running the test suite
To run the test suite, you can run the following command:

```bash
docker-compose -f docker-compose.test.yml up
```