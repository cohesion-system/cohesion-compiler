
#
# A simple demonstration of control flow
#
def workflow(operation, data):
    result = None
    if operation.upper() == 'SORT':
        result = cohesion.Lambda.sort(data)
    else:
        result = data
    return result
