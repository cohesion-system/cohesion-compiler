import json

# Args should look like:
#
# {
#   'latitude': 123,
#   'longitude': 456
# }
def weather(args):
    # Normally, you'd use a secret store (vault, kms etc)
    darkSkyAPIKey = '123'
    
    url = ("https://api.darksky.net/forecast/%s/%s,%s" %
           (darkSkyAPIKey, args['latitude'], args['longitude']))

    result = cohesion.Lambda.darkSkyForecast({
        'apiKey': darkSkyAPIKey,
        'latitude': args['latitude'],
        'longitude': args['longitude'],
    })

    forecast = json.loads(result)
    
    maxTempToday = result['daily']['data']['apparentTemperatureHigh']
    minTempToday = result['daily']['data']['apparentTemperatureLow']

    if maxTempToday > 70:
        cohesion.Lambda.sendSlack("Today's high temp is %s F" % maxTempToday)
    elif minTempToday < 60:
        cohesion.Lambda.sendSlack("Today's low temp is %s F" % minTempToday)

    return forecast
