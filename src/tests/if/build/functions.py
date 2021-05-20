def workflow_func_1(event, context):
    env = event['env']
    env['result'] = None
    env['test_1'] = bool(operation.upper() == 'SORT')
    return {'env': env}


def workflow_func_2(event, context):
    env = event['env']
    env['result'] = env['data']
    return {'env': env}


