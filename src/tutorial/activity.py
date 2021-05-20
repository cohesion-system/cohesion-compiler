#
# A simple demo showing activity invocation
#
def activityWorkflow():
    #
    # Invoke an activity called `getData`, place result in `data`.
    #
    data = cohesion.activity.getData(timeoutSeconds = 120)

    #
    # This will be the result of our step function
    #
    return data
