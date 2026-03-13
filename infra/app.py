import os
import aws_cdk as cdk
from almabani_stack import AlmabaniStack
from pricecode_stack import PriceCodeStack
from pricecode_vector_stack import PriceCodeVectorStack
from deletion_stack import DeletionStack
from chat_stack import ChatStack
from dotenv import load_dotenv

# Load env vars from boq-backend/env (primary) or root .env (fallback)
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'boq-backend', 'env')
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
else:
    # Fallback to root .env
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    load_dotenv(env_path, override=True)

print(f"Loaded environment from: {env_path}")
print(f"OPENAI_CHAT_MODEL: {os.getenv('OPENAI_CHAT_MODEL')}")

app = cdk.App()
account = os.environ.get('CDK_DEFAULT_ACCOUNT', os.getenv('AWS_ACCOUNT_ID', ''))
region = os.environ.get('CDK_DEFAULT_REGION', os.getenv('AWS_REGION', 'eu-west-1'))
if not account:
    raise ValueError(
        "AWS account not set. Either run 'aws configure' or set AWS_ACCOUNT_ID in your env file."
    )
print(f"Deploying to Account: {account}, Region: {region}")
env = cdk.Environment(
    account=account, 
    region=region
)


# Main Almabani Stack (rate filler)
main_stack = AlmabaniStack(app, "AlmabaniStack", env=env)

# Price Code Stack (standalone mode - creates its own VPC/bucket)
pc_stack = PriceCodeStack(app, "PriceCodeStack", env=env)

# Price Code Vector Stack (standalone mode - creates its own VPC/bucket)
pcv_stack = PriceCodeVectorStack(app, "PriceCodeVectorStack", env=env)

# Deletion API Stack
DeletionStack(app, "DeletionStack", env=env, 
              shared_bucket=main_stack.bucket,
              pricecode_bucket=pc_stack.bucket,
              pricecode_vector_bucket=pcv_stack.bucket)

# Chat API Stack (natural language interface)
ChatStack(app, "ChatStack", env=env)

app.synth()
