if 'custom' not in globals():
    from mage_ai.data_preparation.decorators import custom
if 'test' not in globals():
    from mage_ai.data_preparation.decorators import test


@custom
def transform_custom(*args, **kwargs):
    """
    run athena query for data validation
    """
    import awswrangler as wr
    import boto3

    region = "ap-southeast-2"
    session = boto3.Session(region_name=region)
    df = wr.athena.read_Sql_query(
        sql = """
        SELECT
            location,
            temperature,
            humidity,
            date_partition,
            CAST(observation_time AS timestamp) as observation_time,
            CAST(loaded_at AS timestamp) as loaded_at
        FROM cs_workshop_weather.daily_weather_shay
        """,
        database = "cs_workshop_weather",
        boto3_session=session
    )

    return df

