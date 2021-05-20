import ast
import typing
import config

class GenSym:

    def __init__(self, tree: ast.AST):
        names = set([])
        class NameWalker(ast.NodeVisitor):
            def visit_Name(self, node):
                names.add(node.id)
                self.generic_visit(node)
            def visit_FunctionDef(self, node):
                names.add(node.name)
                self.generic_visit(node)

        NameWalker().visit(tree)

        self.names = names


    def sym(self, prefix: str) -> str:
        """
        Generate new unique variable name starting with prefix.
        """
        i = 1
        while True:
            s = "%s_%d" % (prefix, i)
            if s in self.names:
                i += 1
                continue
            self.names.add(s)
            return s

    def dump_names(self):
        print(self.names)

_gensym = None

def gensym_init(cfg: config.Config, tree: ast.AST) -> ast.AST:
    global _gensym
    _gensym = GenSym(tree)
    return tree

def gensym_dump(cfg: config.Config, tree: ast.AST) -> ast.AST:
    _gensym.dump_names()
    return tree

def gensym(prefix: str) -> str:
    return _gensym.sym(prefix)

