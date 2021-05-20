from typing import List
import ast
import coloring
import gensym
import config

class CallLifter(ast.NodeTransformer):
    """Given a node, lift the green calls to a list of statements
    that should be run before that node.

    Useful for e.g. for lifting a call out of arguments to a function,
    or out of an arithmetic expression, and so on.

    This transform does not currently handle short circuit operators.
    To handle that we can add a separate pass before this to transform
    short circuits into if-statements.
    
    How it works -- 

    Roughly anything that has a "body" property -- functions, if,
    loops, with, try -- needs to be transformed.

    For these nodes we have to implement a visitor. that visitor calls
    generic_visit on each node in the body, while keeping track of the
    pre_statements resulting from each visit, and putting them in the
    body in the right place.

    In other words, we're reconstructing every node that has a "body"
    property.

    """
    def __init__(self):
        self.pre_statements = []

    def _transform_sequence(self, nodelist: List[ast.AST]) -> List[ast.AST]:
        """Transform a sequence of AST nodes, visiting each node in the list
        and handling pre_statements.

        """
        newbody = []
        for n in nodelist:
            self.pre_statements = []            # reset pre_statements to empty
            nn = self.visit(n)                  # this _may_ set pre_statements, and returns a replacement
            newbody.extend(self.pre_statements) # first add pre_statements to result, 
            newbody.append(nn)                  # and finally add the transformed node
        self.pre_statements = []
        return newbody

    def visit_FunctionDef(self, node):
        if not coloring.is_green(node):
            return node
        node.body = self._transform_sequence(node.body)
        return node
        
    def visit_For(self, node):
        if not coloring.is_green(node):
            return node
        node.body = self._transform_sequence(node.body)
        node.iter = self.generic_visit(node.iter)
        return node
    
    def visit_If(self, node):
        if not coloring.is_green(node):
            return node

        node.body = self._transform_sequence(node.body)
        node.orelse = self._transform_sequence(node.orelse)

        # transform node test, e.g. if it's a call, this makes sure it's lifted
        node.test = self.visit(node.test)

        # lift the test (possibly again). We simply always do this,
        # because we can't know whether the value in it is a bool or
        # not.
        #
        # TODO: we can be a lot smarter when there are
        # Compare(...constant..) exprs, and transform to SFN's string
        # equality, numeric equality etc operators
        testVar = gensym.gensym("test")
        lifted = ast.Assign(targets=[ast.Name(id=testVar, ctx=ast.Store())],
                        value = ast.Call(func=ast.Name(id='bool', ctx=ast.Load()),
                                         args=[node.test],
                                         keywords=[]))
        ast.copy_location(lifted, node.test)
        
        self.pre_statements.append(lifted)
        node.test = ast.copy_location(ast.Name(id=testVar, ctx=ast.Load()),
                                      node)
        
        return node
    
    def visit_While(self, node):
        if not coloring.is_green(node):
            return node

        # testVar = not bool(...test)
        testVar = gensym.gensym("test")
        testStatement = ast.Assign(
            targets=[ast.Name(id=testVar, ctx=ast.Store())],
            value = ast.UnaryOp(op = ast.Not(),
                                operand = ast.Call(func=ast.Name(id='bool', ctx=ast.Load()),
                                                   args=[node.test],
                                                   keywords=[])))
        ast.copy_location(testStatement, node)
        # TODO testStatement needs to be colored appropriately
        # based on whether test contains green calls        

        # "if <testVar>: break"
        breakNode = ast.Break()
        ast.copy_location(breakNode, node)
        breakNode.color = True
        loopIf = ast.If(test = ast.Name(id = testVar, ctx = ast.Load()),
                        body = [breakNode],
                        orelse = [])
        ast.copy_location(loopIf, node)
        loopIf.color = True

        
        # build the new body
        newbody = []
        newbody.append(testStatement)
        newbody.append(loopIf)
        newbody.extend(node.body)
        node.body = self._transform_sequence(newbody)
        
        node.test = ast.copy_location(ast.NameConstant(value = True), node)
        
        return node

    def visit_Assign(self, node):
        # assignment transforms:
        # if blue do nothing
        # if green and rhs is Call, do nothing
        # if green and rhs is anything else (e.g. a binop), change
        #   color to blue: the call will be lifted out of this assign,
        #   whatever expr it's in.
        if not coloring.is_green(node):
            return node

        if isinstance(node.value, ast.Call):
            return node

        node.color = False
        
        return self.generic_visit(node)

    def _lift_call_args(self, node: ast.Call):
        # lift each arg
        newargs = []
        for arg in node.args:
            if isinstance(arg, ast.Name): # just a name, no need to transform
                newargs.append(arg)
                continue

            # Don't lift constants.
            #
            # TODO -- fix other passes that depend on this being a var
            #
            # if isinstance(node.func, ast.Attribute):
            #     if node.func.attr == 'sleep':
            #         if isinstance(arg, ast.Num):
            #             newargs.append(arg.n)
            #             continue

            # lift anything that's not a name
            argVar = gensym.gensym("a")
            # important to visit the arg node, since it could itself
            # have a call
            lifted = ast.Assign(targets=[ast.Name(id=argVar, ctx=ast.Store())],
                                value = self.visit(arg))
            lifted.color = True # TODO: need to figure out the right color for this node
            ast.copy_location(lifted, node)
            self.pre_statements.append(lifted)
            replacement = ast.copy_location(ast.Name(id = argVar, ctx=ast.Load()), node)
            newargs.append(replacement)

        # replace args 
        node.args = newargs
    
    def visit_Call(self, node):
        """Transform a call into (a) assignments for args (b) standalone call
        (variables in, out) (c) replacement node as tmp var ref

        """
        if not coloring.is_green(node):
            return node

        self._lift_call_args(node)

        # now, the call itself
        resultVar = gensym.gensym("call")
        lifted = ast.Assign(targets=[ast.Name(id=resultVar, ctx=ast.Store())],
                            value=node)
        ast.copy_location(lifted, node)
        lifted.color = True
        self.pre_statements.append(lifted)
        replacement = ast.copy_location(ast.Name(id=resultVar, ctx=ast.Load()), node)
        return replacement


    def visit_Expr(self, node):
        # Special-case void-context calls.  This avoids a whole
        # unnecessary lambda for the very common case of invoking a
        # task and discarding the result.
        v = node.value
        if isinstance(v, ast.Call):
            if not coloring.is_green(v):
                return
            self._lift_call_args(v)
        return node


    def visit_Return(self, node):
        # blue returns are never transformed;
        # green returns are transformed UNLESS:
        #   (a) they return a constant primitive value (num, string, bool, nothing)
        #   (b) they return a variable reference (with no other expression)

        if not coloring.is_green(node):
            return
        
        v = node.value
        if v == None:
            return node
        
        if isinstance(v, ast.Num) or isinstance(v, ast.Str) or isinstance(v, ast.NameConstant):
            return node

        if isinstance(v, ast.Name) and isinstance(v.ctx, ast.Load):
            return node
        
        # return <expr> becomes:
        #  ...
        #  env[var] = transform[<expr>]
        #  return env[var]
        #
        tmpVar = gensym.gensym("ret")

        # node.value may contain green nodes, so we need to visit it
        retvalue = self.visit(node.value)

        if isinstance(retvalue, ast.Name) and isinstance(retvalue.ctx, ast.Load):
            # no further transform needed
            replacement = ast.copy_location(ast.Return(value=retvalue), node)
            replacement.color = True
            return replacement
            
        # we got something more than a name (some sort of expression).
        # lift it out to an assignment.
        lifted = ast.Assign(targets=[ast.Name(id=tmpVar, ctx=ast.Store())],
                            value=retvalue)
        ast.copy_location(lifted, node)
        # I think we don't need to color this because whatever green
        # is in there has been lifted?  Need to prove/disprove this.
        self.pre_statements.append(lifted)
        replacement = ast.Return(value=ast.Name(id=tmpVar, ctx=ast.Load()))
        ast.copy_location(replacement, node)
        replacement.color = True
        return replacement

    def visit_Try(self, node):
        if not coloring.is_green(node):
            return
        node.body = self._transform_sequence(node.body)
        for h in node.handlers:
            h.body = self._transform_sequence(h.body)
        return node
    
def calls(cfg: config.Config, tree: ast.AST) -> ast.AST:
    return CallLifter().visit(tree)
