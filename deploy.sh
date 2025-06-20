﻿#!/bin/bash

# Colores para la salida
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Script de Despliegue Azure App Service for Containers ===${NC}"

# ConfiguraciÃ³n inicial
echo -e "\n${GREEN}Configurando variables...${NC}"
RESOURCE_GROUP="whatsapp-bot-rg"
LOCATION="eastus"  # Cambia segÃºn tu regiÃ³n
ACR_NAME="whatsappbotacr$(date +%s | tail -c 4)"  # Nombre Ãºnico para ACR
APP_SERVICE_PLAN="whatsapp-bot-plan"
WEBAPP_NAME="whatsapp-bot-$(date +%s | tail -c 6)"  # Nombre Ãºnico para Web App
DOCKER_IMAGE="whatsapp-bot-image"
DOCKER_TAG="latest"

# Iniciar sesiÃ³n en Azure
echo -e "\n${GREEN}Iniciando sesiÃ³n en Azure...${NC}"
az login

# Crear Grupo de Recursos
echo -e "\n${GREEN}Creando Grupo de Recursos...${NC}"
az group create --name $RESOURCE_GROUP --location $LOCATION

# Crear Azure Container Registry
echo -e "\n${GREEN}Creando Azure Container Registry...${NC}"
az acr create --resource-group $RESOURCE_GROUP --name $ACR_NAME --sku Basic --admin-enabled true

# Obtener credenciales de ACR
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query "username" -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

# Iniciar sesiÃ³n en Docker con ACR
echo -e "\n${GREEN}Iniciando sesiÃ³n en ACR...${NC}"
docker login $ACR_LOGIN_SERVER -u $ACR_USERNAME -p $ACR_PASSWORD

# Construir y etiquetar la imagen
echo -e "\n${GREEN}Construyendo imagen de Docker...${NC}"
docker build -t $DOCKER_IMAGE:$DOCKER_TAG .

# Etiquetar imagen para ACR
docker tag $DOCKER_IMAGE:$DOCKER_TAG $ACR_LOGIN_SERVER/$DOCKER_IMAGE:$DOCKER_TAG

# Subir imagen a ACR
echo -e "\n${GREEN}Subiendo imagen a ACR...${NC}"
docker push $ACR_LOGIN_SERVER/$DOCKER_IMAGE:$DOCKER_TAG

# Crear App Service Plan
echo -e "\n${GREEN}Creando App Service Plan...${NC}"
az appservice plan create --name $APP_SERVICE_PLAN --resource-group $RESOURCE_GROUP --location $LOCATION --is-linux --sku B1

# Crear Web App for Containers
echo -e "\n${GREEN}Creando Web App for Containers...${NC}"
az webapp create --resource-group $RESOURCE_GROUP --plan $APP_SERVICE_PLAN --name $WEBAPP_NAME --deployment-container-image-name $ACR_LOGIN_SERVER/$DOCKER_IMAGE:$DOCKER_TAG

# Configurar Web App
echo -e "\n${GREEN}Configurando Web App...${NC}"

# Configurar credenciales de ACR
az webapp config container set --name $WEBAPP_NAME --resource-group $RESOURCE_GROUP \
  --docker-custom-image-name $ACR_LOGIN_SERVER/$DOCKER_IMAGE:$DOCKER_TAG \
  --docker-registry-server-url https://$ACR_LOGIN_SERVER \
  --docker-registry-server-user $ACR_USERNAME \
  --docker-registry-server-password $ACR_PASSWORD

# Configurar comando de inicio
az webapp config set --resource-group $RESOURCE_GROUP --name $WEBAPP_NAME --startup-file "./startup.sh"

# Configurar variables de entorno desde .env
echo -e "\n${GREEN}Configurando variables de entorno...${NC}"
while IFS= read -r line || [[ -n "$line" ]]; do
  # Ignorar lÃ­neas vacÃ­as y comentarios
  if [[ -n "$line" && ! "$line" =~ ^[[:space:]]*# ]]; then
    # Escapar comillas dobles en el valor
    key=$(echo $line | cut -d '=' -f1)
    value=$(echo $line | cut -d '=' -f2- | sed 's/"/\\"/g')
    echo "Configurando $key"
    az webapp config appsettings set --name $WEBAPP_NAME --resource-group $RESOURCE_GROUP --settings "$key=$value"
  fi
done < .env

# Habilitar logs
echo -e "\n${GREEN}Habilitando logs...${NC}"
az webapp log config --name $WEBAPP_NAME --resource-group $RESOURCE_GROUP --docker-container-logging filesystem

# Obtener URL de la aplicaciÃ³n
APP_URL=$(az webapp show --name $WEBAPP_NAME --resource-group $RESOURCE_GROUP --query "defaultHostName" -o tsv)

echo -e "\n${GREEN}Â¡Despliegue completado con Ã©xito!${NC}"
echo -e "URL de la aplicaciÃ³n: https://$APP_URL"
echo -e "\n${YELLOW}No olvides configurar el webhook en el portal de Meta for Developers:${NC}"
echo -e "URL de devoluciÃ³n de llamada: https://$APP_URL/api/webhook/whatsapp"
echo -e "Token de verificaciÃ³n: [EL VALOR DE WHATSAPP_VERIFY_TOKEN DE TU .env]"