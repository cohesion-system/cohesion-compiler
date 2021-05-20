
def retryDemo():
    return cohesion.Lambda.foo(timeoutSeconds = 100,
                               heartbeatSeconds = 10,
                               retry = [ { Error: "States.ALL",
                                           IntervalSeconds: 1,
                                           MaxAttempts: 3,
                                           BackoffRate: 2 } ])
