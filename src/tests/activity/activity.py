def activityWorkflow():
    data = cohesion.activity.getData(timeoutSeconds = 120)
    sortedData = cohesion.activity.sortNumbers(data, timeoutSeconds = 120)
    return sortedData
