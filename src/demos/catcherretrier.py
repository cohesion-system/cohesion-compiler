
def go():

    # option 1 -- obvious but not "pythonic"; also, quite ASF specific.
    cohesion.Lambda.foo(
        1, 2, 3,
        retry = [ { Error: "States.TaskFailed",
                    IntervalSeconds: 1,
                    MaxAttempts: 3,
                    BackoffRate: 2 } ])

    # option 2 -- hmm, nah.  we want to see the retry code *after* the important part
    with cohesion.retry(onerror=x, y, z):
        cohesion.Lambda.foo(x,y,z)

    # option 2.1 -- intriguing but still a bit weird
    # e.g. what if there are two calls in here
    while cohesion.retry():
        cohesion.Lambda.foo()

    # option 3 -- ugh wtf
    @retry(States.TaskFailed, i = 1, n = 3, rate = 2)
    def f():
        cohesion.Lambda.foo(1,2,3)
    f()

    # option 4 -- close but just too strange
    try:
        cohesion.Lambda.foo(1,2,3)
    except States.TaskFailed:
        cohesion.retry(intervalSec = 1, maxAttempts = 3, backoffRate = 2)

    # option 5 -- feels nice because retry feels like config
    # anyway. makes things a bit invisible though, when you're in the
    # code.  Also now you have to carefully maintain a config file
    # next to the source.
    cohesion.Lambda.foo(1,2,3)

    # --- config.yaml file
    retriers:
    - cohesion.Lambda.foo
      - States.TaskFailed
        IntervalSeconds: 1
        MaxAttempts: 3
        BackoffRate: 2

    # retrier decision: implement option 1.  maybe add 5 later.


    #
    # Catchers
    #
    # Catchers are trickier because they have a "next" property and
    # we're hiding state names from programmers.  We do not provide a
    # strict equivalent, but we still need to give users a way to
    # handle failures of tasks.  The pythonic way of course is to use
    # try/except.
    #
    # For now we won't support `finally`.  But it can be handled of
    # course, we just need a way to "reraise" errors.  This is easy if
    # there's no nested try -- you just exit.  But with nested try we
    # have to keep some stack of exception targets and emit edges to
    # that on error.  Also doable, but a bit complex.
    #

    try:
        cohesion.Lambda.x()
    except States.ALL as error:
        # err handling code goes here
        stuff

    # but then what about this:
    try:
        cohesion.Lambda.x()
        cohesion.Lambda.y()
    except States.ALL as error:
        return error

    # i think we'll need a try/except in the CAST

    # and then handle it in cast->asfast

    # every step's gets a catcher, and the "next" points at the next
    # thing in the sequence

    # this complicates things a bit, overall.

    # so for now let's just support try-catch with only one statement
    # inside, and that statement has to be a task (this automatically
    # eliminates nesting too)
