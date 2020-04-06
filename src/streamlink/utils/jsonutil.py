import esprima.parser
import esprima.error_handler
import logging
import numbers

log = logging.getLogger(__name__)


def _parse_array(expression, jsobj):
    return [_parse_expression(element, jsobj) for element in expression.elements]


def _parse_expression(expression, jsobj):
    if expression.type == "Literal":
        return expression.value

    if expression.type == "ArrayExpression":
        return _parse_array(expression, jsobj)

    if expression.type == "Identifier":
        return expression.name

    if expression.type == "ObjectExpression":
        return _parse_object(expression, jsobj)

    if expression.type == "UnaryExpression":
        if (expression.prefix and
                expression.operator in ("+", "-") and
                expression.argument.type == "Literal" and
                isinstance(expression.argument.value, numbers.Complex)):

            return {"+": expression.argument.value,
                    "-": -expression.argument.value}[expression.operator]

    unparsed = jsobj[expression.range[0]:expression.range[1]]

    log.warning("Failed to parse {0} snippet: {1}".format(expression.type, unparsed))

    return unparsed


def _parse_property(property, jsobj):
    return _parse_expression(property.key, jsobj), _parse_expression(property.value, jsobj)


def _parse_object(object, jsobj):
    r = {}
    for property in object.properties:
        key, value = _parse_property(property, jsobj)
        r[key] = value
    return r


def from_js(jsobj, parser_options=None):
    parser_options = parser_options or {}
    parser_options["range"] = True
    parser = esprima.parser.Parser(jsobj, parser_options)
    try:
        if parser.lookahead.value == "{":
            parsed = parser.parseObjectInitializer()
            return _parse_object(parsed, jsobj)
        elif parser.lookahead.value == "[":
            parsed = parser.parseArrayInitializer()
            return _parse_array(parsed, jsobj)
        else:
            raise parser.unexpectedTokenError(parser.nextToken())
    except esprima.error_handler.Error as e:
        raise ValueError("Unable to parse to python dict: {}".format(e))
