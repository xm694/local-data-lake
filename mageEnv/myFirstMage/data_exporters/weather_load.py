
import os
import logging
import pandas as pd
from datetime import datetime
from pyiceberg.catalog import load_catalog
from pyiceberg.schema import Schema
from pyiceberg.types import (
    NestedField, StringType, IntegerType, FloatType, TimestampType, DoubleType
)
from pyiceberg.partitioning import PartitionSpec, PartitionField
from pyiceberg.exceptions import NoSuchTableError, NamespaceAlreadyExistsError
import pyarrow as pa

if 'data_exporter' not in globals():
    from mage_ai.data_preparation.decorators import data_exporter

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iceberg_exporter")

@data_exporter
def export_data(data, *args, **kwargs):

    if isinstance(data, list):
        df = pd.DataFrame(data)
    else:
        df = data.copy()

    # Convert data type to makesure matching schema
    # df['temperature'] = df['temperature'].astype('float32') 
    df['observation_time'] = df['observation_time'].dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
    df['loaded_at'] = pd.to_datetime(df['loaded_at']).dt.strftime('%Y-%m-%dT%H:%M:%S.%f')

    """
    Exports data to some source.

    Args:
        data: The output from the upstream parent block
        args: The output from any additional upstream blocks (if applicable)

    Output (optional):
        Optionally return any object and it'll be logged and
        displayed when inspecting the block run.
    """

    # Get environment variables with proper validation
    namespace = os.environ.get('ICEBERG_DATABASE', 'mage-demo')
    table_name = os.environ.get('ICEBERG_TABLE', 'daily_weather_shay')
    warehouse_location = os.environ.get('ICEBERG_WAREHOUSE', 'mage-warehouse')
    lakekeeper_base_uri = os.environ.get('ICEBERG_REST_URI', 'http://lakekeeper:8181')
    # s3_endpoint = os.environ.get('AWS_ENDPOINT_URL', 'http://minio:9000')
    # aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID', 'minioadmin')
    # aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY', 'minioadmin')

    # Set S3/AWS credentials as environment variables
    # This ensures they're available to all underlying libraries including s3fs
    os.environ['AWS_ACCESS_KEY_ID'] = os.environ.get('AWS_ACCESS_KEY_ID', 'minioadmin')
    os.environ['AWS_SECRET_ACCESS_KEY'] = os.environ.get('AWS_SECRET_ACCESS_KEY', 'minioadmin')
    os.environ['AWS_ENDPOINT_URL'] = os.environ.get('AWS_ENDPOINT_URL', 'http://minio:9000')
    
    s3_endpoint = os.environ['AWS_ENDPOINT_URL']
    
    # Print configuration for debugging
    logger.info(f"Using S3 endpoint: {s3_endpoint}")
    logger.info(f"Target table: {namespace}.{table_name}")
    logger.info(f"Warehouse location: {warehouse_location}")

    try:
        # connect to the Lakekeeper catalog
        catalog = load_catalog(
            'rest',
            **{
                "uri": f"{lakekeeper_base_uri}/catalog",
                "warehouse": warehouse_location,
                "s3.endpoint": s3_endpoint,
                "s3.path-style-access": "true",
                "s3.region": "ap-southeast-2",
                "client.region": "ap-southeast-2",
                "s3.remote-signing-enabled": "false"  # Disable for MinIO
                # Not setting credentials here - will be picked up from environment
                # "s3.access-key-id": aws_access_key,
                # "s3.secret-access-key": aws_secret_key,
            }
        )
        logger.info("Available warehouses:")
        # Print warehouses if method exists
        if hasattr(catalog, "list_warehouses"):
            logger.info(catalog.list_warehouses())
        logger.info("Available namespaces:")
        logger.info(catalog.list_namespaces())

        # Step 1: Ensure namespace exists
        try:
            namespaces = catalog.list_namespaces()
            logger.info(f"Available namespaces: {namespaces}")

            if (namespace,) not in namespaces:
                logger.info(f"Creating namespace: {namespace}")
                catalog.create_namespace(namespace)
                logger.info(f"Successfully created namespace: {namespace}")
            else:
                logger.info(f"Namespace {namespace} already exists")
        except NamespaceAlreadyExistsError:
            logger.info(f"Namespace {namespace} already exists")
        except Exception as e:
            logger.error(f"Error handling namespace: {str(e)}")
            raise

        # Step 2: Define schema based on df from transformer
        expected_columns = ['location', 'temperature', 'humidity', 'observation_time', 'loaded_at', 'date_partition']
        for col in expected_columns:
            if col not in df.columns:
                raise ValueError(f"Required column '{col}' is missing from the DataFrame")
            
        # Define schema fields with proper types
        schema = Schema(
            NestedField(1, "location", StringType(), required=False),
            NestedField(2, "temperature", DoubleType(), required=False),
            NestedField(3, "humidity", IntegerType(), required=False),
            NestedField(4, "observation_time", StringType(), required=False),
            NestedField(5, "loaded_at", StringType(), required=False),
            NestedField(6, "date_partition", StringType(), required=False)
        )

        # Step 3: Create or append to table
        table_identifier = f"{namespace}.{table_name}"
        try:
            # check if table exists
            table = catalog.load_table(table_identifier)
            logger.info(f"Table {table_identifier} exists, appending data")

            # Convert df to PyArrow table for efficient writing
            arrow_schema = pa.schema([
                ('location', pa.string()),
                ('temperature', pa.float64()),
                ('humidity', pa.int32()),
                ('observation_time', pa.string()),
                ('loaded_at', pa.string()),
                ('date_partition', pa.string())
            ])
            arrow_table = pa.Table.from_pandas(df, schema=arrow_schema)
            table.append(arrow_table)

            # Append table to existing table
            # with table.append(arrow_table) as append_op:
            #     append_op.append_table(arrow_table)
            #     metrics = append_op.commit()
            # logger.info(f"Append operation metrics: {metrics}")

        except NoSuchTableError:
            logger.info(f"Table {table_identifier} does not exist, creating new table")

            # Create partition by date_partition
            partition_field = PartitionField(
                source_id=6,  # source_id for date_partition field
                field_id=1000,  # A unique field_id for this partition field
                transform="identity",
                name="date_partition"
            )
            partition_spec = PartitionSpec(partition_field)

            properties = {
                'format-version': '2',
                'write.parquet.compression-codec': 'gzip',
                'write.metadata.compression-codec': 'gzip'
            }

            # create table
            table = catalog.create_table(
                identifier=table_identifier,
                schema=schema,
                partition_spec=partition_spec,
                properties=properties
            )
            logger.info(f"Successfully created table {table_identifier}")

            # convert and append table
            arrow_schema = pa.schema([
                ('location', pa.string()),
                ('temperature', pa.float64()),
                ('humidity', pa.int32()),
                ('observation_time', pa.string()),
                ('loaded_at', pa.string()),
                ('date_partition', pa.string())
            ])
            arrow_table = pa.Table.from_pandas(df, schema=arrow_schema)
            table.append(arrow_table)

            # # Append table to existing table
            # with table.append(arrow_table) as append_op:
            #     append_op.append_table(arrow_table)
            #     metrics = append_op.commit()

            # logger.info(f"Initial write operation metrics: {metrics}")

    except Exception as e:
        error_msg = f"Failed to write data to table {namespace}.{table_name}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    logger.info(f"Successfully exported {len(df)} records to {namespace}.{table_name}")
    return df
            