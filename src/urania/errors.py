"""Errors that Urania shows to the user. The message must tell the user what to do."""


class UraniaError(Exception):
    """A problem with an input file, a tool or the system. The message is for the user."""


class ToolMissing(UraniaError):
    """A Vulkan tool (glslangValidator, spirv-val, spirv-cross) is not found or does not run."""
