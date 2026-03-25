; Top-level function signatures
(function_signature
  name: (identifier) @function.name
) @function.def

; Class definitions
(class_definition
  name: (identifier) @class.name
) @class.def

; Method signatures inside class bodies
(method_signature
  (function_signature
    name: (identifier) @method.name
  )
) @method.def

; Constructor signatures
(constructor_signature
  name: (identifier) @constructor.name
) @constructor.def

; Import statements
(import_or_export
  (library_import
    (import_specification) @import.spec
  )
) @import.def

; Documentation comments
(documentation_comment) @doc_comment
