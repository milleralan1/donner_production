#!/bin/bash
set -e

ENVIRONMENT=${1:-dev}          # dev | test | prod
PROJECT_NAME=${2:-twin}
RESOURCE_SUFFIX=${RESOURCE_SUFFIX:-01}

echo "🚀 Deploying ${PROJECT_NAME} to ${ENVIRONMENT} (suffix: ${RESOURCE_SUFFIX})..."

# 1. Terraform workspace & apply
cd "$(dirname "$0")/../terraform"
terraform init -input=false

if ! terraform workspace list | grep -q "$ENVIRONMENT"; then
  terraform workspace new "$ENVIRONMENT"
else
  terraform workspace select "$ENVIRONMENT"
fi

# Use prod.tfvars for production environment
if [ "$ENVIRONMENT" = "prod" ]; then
  TF_APPLY_CMD=(terraform apply -var-file=prod.tfvars -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -var="resource_suffix=$RESOURCE_SUFFIX" -auto-approve)
else
  TF_APPLY_CMD=(terraform apply -var="project_name=$PROJECT_NAME" -var="environment=$ENVIRONMENT" -var="resource_suffix=$RESOURCE_SUFFIX" -auto-approve)
fi

echo "🎯 Applying Terraform..."
"${TF_APPLY_CMD[@]}"

API_URL=$(terraform output -raw cloud_run_url)

# 2. Build + deploy frontend
cd ../frontend

# Create production environment file with API URL
echo "📝 Setting API URL for production..."
echo "NEXT_PUBLIC_API_URL=$API_URL" > .env.production

npm install
npm run build
firebase deploy --only "hosting:${ENVIRONMENT}"
cd ..

# 3. Final messages
SITE_NAME="${PROJECT_NAME}-${ENVIRONMENT}-${RESOURCE_SUFFIX}"
HOSTING_URL=$(firebase hosting:sites:list --json 2>/dev/null | grep -A2 "\"${SITE_NAME}\"" | grep defaultUrl | sed -E 's/.*"(https:[^"]+)".*/\1/' || echo "https://${SITE_NAME}.web.app")
echo -e "\n✅ Deployment complete!"
echo "🌐 Firebase Hosting URL : $HOSTING_URL"
echo "📡 Cloud Run URL        : $API_URL"
