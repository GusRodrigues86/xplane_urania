# =====================================================================================
# Urania - X-Plane 12 plugin (night sky settings, sky file check and restore). CMake build file.
#
# Targets:
#   urania_core    static library without X-Plane calls (xsa_gains, sky_files). The tests use it.
#   urania_tests   unit tests for urania_core (CTest). They need no X-Plane SDK.
#   Urania         the plugin Urania.xpl (needs the X-Plane SDK 4.4: X-Plane 12.4.4 or newer).
#
# The plugin is copied into the X-Plane folder layout:
#   dist/Urania/win_x64/Urania.xpl    (Windows)
#   dist/Urania/lin_x64/Urania.xpl    (Linux)
#
# Build commands (scripts/build_plugin.py runs them):
#   cmake --preset windows     then   cmake --build --preset windows   then   ctest --preset windows
#   cmake --preset linux       then   cmake --build --preset linux     then   ctest --preset linux
# =====================================================================================
cmake_minimum_required(VERSION 3.21)

project(Urania VERSION 1.0.1 LANGUAGES CXX)

if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "build type" FORCE)
endif()

option(URANIA_PLUGIN "Build the plugin Urania.xpl (needs the X-Plane SDK)" ON)
option(URANIA_TESTS "Build the unit tests (no SDK needed)" ON)
option(URANIA_DEV "Urania test parts in the settings window" OFF)

if(WIN32)
  set(URANIA_PLATFORM_DEFS IBM=1 APL=0 LIN=0 _USE_MATH_DEFINES NOMINMAX _CRT_SECURE_NO_WARNINGS)
  set(XPL_FOLDER win_x64)
elseif(APPLE)
  set(URANIA_PLATFORM_DEFS IBM=0 APL=1 LIN=0)
  set(XPL_FOLDER mac_x64)
else()
  set(URANIA_PLATFORM_DEFS IBM=0 APL=0 LIN=1)
  set(XPL_FOLDER lin_x64)
endif()

function(urania_compile_options target)
  target_compile_definitions(${target} PRIVATE ${URANIA_PLATFORM_DEFS})
  set_target_properties(${target} PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED ON)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /utf-8 /permissive-)
    # Static C++ runtime: the user does not need the Visual C++ Redistributable.
    set_property(TARGET ${target} PROPERTY MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra)
  endif()
endfunction()

# =====================================================================================
# 1. CORE LIBRARY (no X-Plane calls)
# =====================================================================================
add_library(urania_core STATIC src/xsa_gains.cpp src/xsa_gains.h src/sky_files.cpp src/sky_files.h)
target_include_directories(urania_core PUBLIC src)
set_target_properties(urania_core PROPERTIES POSITION_INDEPENDENT_CODE ON CXX_VISIBILITY_PRESET hidden)
urania_compile_options(urania_core)

# =====================================================================================
# 2. TESTS
# =====================================================================================
if(URANIA_TESTS)
  enable_testing()
  add_executable(urania_tests tests/test_core.cpp)
  target_link_libraries(urania_tests PRIVATE urania_core)
  urania_compile_options(urania_tests)
  add_test(NAME urania_core COMMAND urania_tests "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures")
endif()

# =====================================================================================
# 3. PLUGIN
# =====================================================================================
if(NOT URANIA_PLUGIN)
  return()
endif()

set(XPLANE_SDK_DIR "${CMAKE_CURRENT_SOURCE_DIR}/SDK" CACHE PATH "X-Plane SDK folder (holds CHeaders and Libraries)")
set(SDK "${XPLANE_SDK_DIR}")
if(NOT EXISTS "${SDK}/CHeaders" AND EXISTS "${SDK}/SDK/CHeaders")
  set(SDK "${SDK}/SDK")
endif()

set(SDK_FILES CHeaders/XPLM/XPLMPlugin.h CHeaders/XPLM/XPLMDataAccess.h CHeaders/XPLM/XPLMMenus.h)
if(WIN32)
  list(APPEND SDK_FILES Libraries/Win/XPLM_64.lib)
elseif(APPLE)
  list(APPEND SDK_FILES Libraries/Mac/XPLM.framework)
endif()
set(SDK_MISSING "")
foreach(f IN LISTS SDK_FILES)
  if(NOT EXISTS "${SDK}/${f}")
    string(APPEND SDK_MISSING "    ${f}\n")
  endif()
endforeach()
if(SDK_MISSING)
  message(FATAL_ERROR
    "\nX-Plane SDK not found, or not complete.\nSDK folder: ${XPLANE_SDK_DIR}\nMissing files:\n${SDK_MISSING}\n"
    "Download the X-Plane SDK 4.4 or newer (https://developer.x-plane.com/sdk/plugin-sdk-downloads/),\n"
    "then run: python scripts/build_plugin.py --sdk <folder with CHeaders and Libraries>\n"
    "Or configure with -DURANIA_PLUGIN=OFF to build only the tests.\n")
endif()
if(NOT EXISTS "${SDK}/CHeaders/XPLM/XPLMPanelGraphics.h")
  message(FATAL_ERROR "\nUrania needs the X-Plane SDK 4.4 (X-Plane 12.4.4): ${SDK} is older.\n")
endif()
message(STATUS "Urania: X-Plane SDK OK (${SDK})")

set(IMGUI_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/imgui")
add_library(Urania MODULE
  src/urania.cpp
  src/imgui_xplm.cpp
  src/imgui_xplm.h
  "${IMGUI_DIR}/imgui.cpp"
  "${IMGUI_DIR}/imgui_draw.cpp"
  "${IMGUI_DIR}/imgui_tables.cpp"
  "${IMGUI_DIR}/imgui_widgets.cpp")
target_link_libraries(Urania PRIVATE urania_core)
urania_compile_options(Urania)

set_target_properties(Urania PROPERTIES
  PREFIX ""                          # Urania.xpl, not libUrania.xpl
  SUFFIX ".xpl"
  CXX_VISIBILITY_PRESET hidden       # export only the 5 X-Plane functions (PLUGIN_API)
  VISIBILITY_INLINES_HIDDEN ON)

target_include_directories(Urania PRIVATE "${SDK}/CHeaders/XPLM" "${IMGUI_DIR}")

# X-Plane 12.4.4 renders the ImGui window (SDK 4.4 XPLMPanelGraphics).
target_compile_definitions(Urania PRIVATE
  XPLM200=1 XPLM210=1 XPLM300=1 XPLM301=1 XPLM302=1 XPLM303=1 XPLM400=1 XPLM410=1 XPLM411=1 XPLM420=1 XPLM430=1 XPLM440=1
  IMGUI_DISABLE_WIN32_DEFAULT_IME_FUNCTIONS IMGUI_DISABLE_DEFAULT_SHELL_FUNCTIONS IMGUI_DISABLE_OBSOLETE_FUNCTIONS
  URANIA_NATIVE_IMGUI=1
  URANIA_DEV=$<BOOL:${URANIA_DEV}>
  URANIA_VERSION="${PROJECT_VERSION}")

if(WIN32)
  target_link_libraries(Urania PRIVATE "${SDK}/Libraries/Win/XPLM_64.lib")
elseif(APPLE)
  target_link_libraries(Urania PRIVATE "${SDK}/Libraries/Mac/XPLM.framework")
else()
  # Linux needs no SDK library: X-Plane gives the functions when it loads the plugin.
  # Put the C++ runtime into the plugin: no dependency on the libstdc++ version of the system.
  target_link_options(Urania PRIVATE -static-libgcc -static-libstdc++)
endif()

set(DIST_DIR "${CMAKE_CURRENT_SOURCE_DIR}/dist/Urania")
add_custom_command(TARGET Urania POST_BUILD
  COMMAND "${CMAKE_COMMAND}" -E make_directory "${DIST_DIR}/${XPL_FOLDER}"
  COMMAND "${CMAKE_COMMAND}" -E copy_if_different "$<TARGET_FILE:Urania>" "${DIST_DIR}/${XPL_FOLDER}/Urania.xpl"
  COMMENT "Urania: copy the plugin to ${DIST_DIR}/${XPL_FOLDER}/Urania.xpl")
