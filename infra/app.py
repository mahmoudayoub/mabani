import os
import aws_cdk as cdk
from almabani_stack import AlmabaniStack
from pricecode_stack import PriceCodeStack
from dotenv import load_dotenv

# Load env vars from project root
# .env is in parent directory relative to infra/
# We moved env to backend/env
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', 'env')
load_dotenv(env_path)

# Also check .env file if env was just a flat file without .env extension
if not os.path.exists(env_path):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    load_dotenv(env_path)

app = cdk.App()
account = '239146712026'
region = 'eu-west-1'
print(f"Deploying to Account: {account}, Region: {region}")
# Use the current account/region
env = cdk.Environment(
    account=account, 
    region=region
)

# Main Almabani Stack (rate filler)
AlmabaniStack(app, "AlmabaniStack", env=env)

# Price Code Stack (standalone mode - creates its own VPC/bucket)
# To share VPC/bucket with main stack, pass shared_vpc and shared_bucket parameters
PriceCodeStack(app, "PriceCodeStack", env=env)

app.synth()
