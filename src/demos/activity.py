#
# A simple demo showing a workflow co-ordinating two activities
#
def activityWorkflow():
    #
    # Invoke an activity called `getData`, place result in `data`.
    #
    data = cohesion.activity.getData(timeoutSeconds = 120)

    #
    # Pass data to another activity called `sortNumbers`, place result
    # in `sortedData`
    #
    sortedData = cohesion.activity.sortNumbers(data, timeoutSeconds = 120)

    #
    # This will be the result of our step function
    #
    return sortedData
