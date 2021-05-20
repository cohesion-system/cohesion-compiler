# Entry point of a serverless workflow
def workflow():
    #
    # Call an AWS Lambda function and store the result
    #
    result = cohesion.Lambda.hello()

    #
    # Return the result from our step function
    #
    return result
