; Package declaration
(package_declaration
  (scoped_identifier) @package.name
) @package.def

; Import declarations
(import_declaration
  (scoped_identifier) @import.name
) @import.def

; Class declarations
(class_declaration
  name: (identifier) @class.name
) @class.def

; Interface declarations
(interface_declaration
  name: (identifier) @interface.name
) @interface.def

; Method declarations
(method_declaration
  name: (identifier) @method.name
) @method.def

; Constructor declarations
(constructor_declaration
  name: (identifier) @constructor.name
) @constructor.def

; Method invocations
(method_invocation
  name: (identifier) @call.name
) @call.def

; Object creation (new Foo())
(object_creation_expression
  type: (type_identifier) @new.name
) @new.def

; Annotations (for detecting @Test)
(marker_annotation
  name: (identifier) @annotation.name
) @annotation.def
