def go_func_1(event, context):
    env = event['env']
    env['a'] = env['myParam'] + 42
    return {'env': env}


def go_func_2(event, context):
    env = event['env']
    env['b'] = env['a'] + env['call_1']
    env['ret_1'] = env['b'] + 1
    return {'env': env}


