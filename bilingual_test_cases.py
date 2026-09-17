"""Test-only Python correspondence for native and browser translation checks."""
import ast


class DisplayStrings(ast.NodeTransformer):
    """Ignore localized display text without ignoring data literals or behavior."""
    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == 'print':
            node.args = [ast.Constant(value='<display>')
                         if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                         else arg for arg in node.args]
        return node

    def visit_Assert(self, node):
        self.generic_visit(node)
        if node.msg is not None:
            node.msg = ast.Constant(value='<assertion message>')
        return node

    def visit_Raise(self, node):
        self.generic_visit(node)
        if isinstance(node.exc, ast.Call):
            node.exc.args = [ast.Constant(value='<error message>')
                             if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                             else arg for arg in node.exc.args]
        return node


def correspondence(portuguese, english, initial=None):
    """Reject changes to algorithm, exact data, SDK calls or control flow."""
    names = dict(initial or {})
    left = DisplayStrings().visit(ast.parse(portuguese))
    right = DisplayStrings().visit(ast.parse(english))

    def compare(a, b, path='module'):
        assert type(a) is type(b), f'{path}: {type(a).__name__} != {type(b).__name__}'
        if isinstance(a, ast.AST):
            for field in a._fields:
                x, y = getattr(a, field), getattr(b, field)
                identifier = ((isinstance(a, ast.Name) and field == 'id') or
                              (isinstance(a, (ast.FunctionDef, ast.AsyncFunctionDef)) and field == 'name') or
                              (isinstance(a, ast.arg) and field == 'arg') or
                              (isinstance(a, ast.alias) and field == 'asname' and x is not None))
                if identifier:
                    assert isinstance(y, str), f'{path}.{field}: missing identifier'
                    assert names.setdefault(x, y) == y, f'{path}: inconsistent rename {x}: {names[x]} / {y}'
                else:
                    compare(x, y, path + '.' + field)
        elif isinstance(a, list):
            assert len(a) == len(b), f'{path}: {len(a)} != {len(b)} items'
            for i, (x, y) in enumerate(zip(a, b)):
                compare(x, y, f'{path}[{i}]')
        else:
            assert a == b, f'{path}: changed semantic value {a!r} -> {b!r}'

    compare(left, right)
    return names


class Rename(ast.NodeTransformer):
    def __init__(self, names):
        self.names = names

    def visit_Name(self, node):
        node.id = self.names.get(node.id, node.id)
        return node

    def visit_arg(self, node):
        node.arg = self.names.get(node.arg, node.arg)
        return node

    def visit_FunctionDef(self, node):
        node.name = self.names.get(node.name, node.name)
        return self.generic_visit(node)

    def visit_alias(self, node):
        if node.asname:
            node.asname = self.names.get(node.asname, node.asname)
        return node


def renamed(source, names):
    return ast.unparse(Rename(names).visit(ast.parse(source)))
