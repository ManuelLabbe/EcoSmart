PROFILE   = labbelopez.manuel@gmail.com
REGION    = us-east-1
STACK     = ecosmart-infra
ACCOUNT_ID = $(shell aws sts get-caller-identity --profile $(PROFILE) --query Account --output text)

# ── Deploy / destroy ───────────────────────────────────────────────────────────

deploy:
	@echo "Desplegando stack $(STACK)..."
	sam deploy \
		--template-file template.yaml \
		--stack-name $(STACK) \
		--capabilities CAPABILITY_NAMED_IAM \
		--region $(REGION) \
		--profile $(PROFILE) \
		--parameter-overrides \
			KeyPairName=$(KEY_PAIR) \
			AllowedCidr=$(shell curl -s https://checkip.amazonaws.com)/32 \
		--resolve-s3

destroy:
	@echo "Eliminando stack $(STACK)..."
	aws cloudformation delete-stack \
		--stack-name $(STACK) \
		--region $(REGION) \
		--profile $(PROFILE)

# ── EC2: encender / apagar ─────────────────────────────────────────────────────

INSTANCE_ID = $(shell aws cloudformation describe-stack-resource \
	--stack-name $(STACK) \
	--logical-resource-id MetabaseInstance \
	--query StackResourceDetail.PhysicalResourceId \
	--output text --region $(REGION) --profile $(PROFILE))

start:
	@echo "Encendiendo instancia EC2..."
	aws ec2 start-instances --instance-ids $(INSTANCE_ID) --region $(REGION) --profile $(PROFILE)
	@echo "Esperando que levante (~60s)..."
	aws ec2 wait instance-running --instance-ids $(INSTANCE_ID) --region $(REGION) --profile $(PROFILE)
	@$(MAKE) url

stop:
	@echo "Apagando instancia EC2 (solo pagas el disco ~$1.60/mes)..."
	aws ec2 stop-instances --instance-ids $(INSTANCE_ID) --region $(REGION) --profile $(PROFILE)

url:
	@echo ""
	@echo "Metabase URL:"
	@aws cloudformation describe-stacks \
		--stack-name $(STACK) \
		--query "Stacks[0].Outputs[?OutputKey=='MetabaseURL'].OutputValue" \
		--output text --region $(REGION) --profile $(PROFILE)
	@echo "(Metabase tarda ~3 min en iniciar la primera vez)"

ssh:
	@SSH_CMD=$$(aws cloudformation describe-stacks \
		--stack-name $(STACK) \
		--query "Stacks[0].Outputs[?OutputKey=='SSHCommand'].OutputValue" \
		--output text --region $(REGION) --profile $(PROFILE)); \
	echo "$$SSH_CMD"; \
	eval "$$SSH_CMD"

# ── Datos ──────────────────────────────────────────────────────────────────────

upload:
	@bash scripts/upload_data.sh $(ACCOUNT_ID) $(REGION)

status:
	@aws cloudformation describe-stacks \
		--stack-name $(STACK) \
		--query "Stacks[0].{Status:StackStatus,Created:CreationTime}" \
		--output table --region $(REGION) --profile $(PROFILE)
	@echo ""
	@aws ec2 describe-instances \
		--instance-ids $(INSTANCE_ID) \
		--query "Reservations[0].Instances[0].{State:State.Name,IP:PublicIpAddress,Type:InstanceType}" \
		--output table --region $(REGION) --profile $(PROFILE)

.PHONY: deploy destroy start stop url ssh upload status
