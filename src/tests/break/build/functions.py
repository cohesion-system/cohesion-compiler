def loopWorkflow_func_1(event, context):
    env = event['env']
    env['sum'] = 0
    return {'env': env}


def loopWorkflow_func_2(event, context):
    env = event['env']
    env['test_1'] = not bool(True)
    env['test_2'] = bool(env['test_1'])
    return {'env': env}


def loopWorkflow_func_3(event, context):
    env = event['env']
    env['sum'] += env['call_1']
    env['test_4'] = bool(env['sum'] > 10)
    return {'env': env}


def loopWorkflow_func_4(event, context):
    env = event['env']
    env['test_3'] = bool(env['sum'] < 15)
    return {'env': env}


def loopWorkflow_func_5(event, context):
    env = event['env']
    env['sum'] += 1
    return {'env': env}


