from aws_cdk import BundlingOptions, aws_lambda as _lambda
from constructs import Construct
import os


def build_async_aws_dependencies_layer(
    scope: Construct, construct_id: str, description: str
) -> _lambda.LayerVersion:
    layer_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "layers", "deletion_dependencies"
    )

    return _lambda.LayerVersion(
        scope,
        construct_id,
        code=_lambda.Code.from_asset(
            layer_dir,
            bundling=BundlingOptions(
                image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                command=[
                    "bash",
                    "-lc",
                    "python -m pip install -r /asset-input/requirements.txt -t /asset-output/python",
                ],
            ),
        ),
        compatible_runtimes=[_lambda.Runtime.PYTHON_3_11],
        description=description,
    )
