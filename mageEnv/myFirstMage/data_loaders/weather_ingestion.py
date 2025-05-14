import pandas as pd
from datetime import datetime
import requests
if 'data_loader' not in globals():
    from mage_ai.data_preparation.decorators import data_loader
if 'test' not in globals():
    from mage_ai.data_preparation.decorators import test


@data_loader
def load_data_from_api(*args, **kwargs):
    """
    Template for loading data from API
    """
    API_KEY = "YOU_API_KEY"
    BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

    cities = [
        {'name':'Sydney', 'lat': -33.8688, 'lon':151.2093},
        {'name':'Melboure', 'lat': -37.6699, 'lon':144.8403},
        {'name':'Perth', 'lat': -31.9514, 'lon':115.8617},
        {'name':'GoldCoast', 'lat': -27.9769, 'lon':153.3809},
        {'name':'Alice Spring', 'lat': -23.6980, 'lon':133.8807},
    ]
    
    weather_data = []
    for city in cities:
        response = requests.get(f"{BASE_URL}?q={','.join([city['name'] for city in cities])}&appid={API_KEY}")
        data = response.json()
        weather_data.append({
            'location': city['name'],
            'temperature': data['main']['temp'],
            'humidity': data['main']['humidity']
        })

    return pd.DataFrame(weather_data)


@test
def test_output(output, *args) -> None:
    """
    Template code for testing the output of the block.
    """
    assert output is not None, 'The output is undefined'
