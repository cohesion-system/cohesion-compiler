

def loopWorkflow(arg):
    sum = 0
    while sum:
        sum += cohesion.Lambda.doStuff()
        if sum > 10:
            if sum < 15:
                break
            else:
                sum += 1
 
