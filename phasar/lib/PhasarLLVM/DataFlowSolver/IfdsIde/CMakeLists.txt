file(GLOB_RECURSE IFDSIDE_SRC *.h *.cpp)

find_package(Boost COMPONENTS program_options REQUIRED)

if(NOT DEFINED CT_SVF_ROOT)
  # CMAKE_SOURCE_DIR is the top-level phasar/ directory
  set(CT_SVF_ROOT "${CMAKE_SOURCE_DIR}/../Extern_PTA/SVF")
endif()
# Prefer conda libz3; fall back to SVF's bundled z3.obj
if(DEFINED ENV{CONDA_PREFIX} AND EXISTS "$ENV{CONDA_PREFIX}/lib/libz3.so")
  set(CT_Z3_LIB "$ENV{CONDA_PREFIX}/lib/libz3.so")
elseif(EXISTS "${CT_SVF_ROOT}/z3.obj/bin/libz3.so")
  set(CT_Z3_LIB "${CT_SVF_ROOT}/z3.obj/bin/libz3.so")
else()
  set(CT_Z3_LIB "z3")
endif()

set(PHASAR_LINK_LIBS
  phasar_config
  phasar_utils
  phasar_pointer
  phasar_typehierarchy
  phasar_controlflow
  phasar_phasarllvm_utils
  phasar_db
  phasar_taintconfig
  ${Boost_LIBRARIES}
        ${CT_SVF_ROOT}/Release-build/svf-llvm/libSvfLLVM.a
        ${CT_SVF_ROOT}/Release-build/svf/libSvfCore.a
        ${CT_Z3_LIB}
)

set(LLVM_LINK_COMPONENTS
  Core
  Support
  Demangle
)


if(BUILD_SHARED_LIBS)
  add_phasar_library(phasar_ifdside
    SHARED
    ${IFDSIDE_SRC}
  )
else()
  add_phasar_library(phasar_ifdside
    STATIC
    ${IFDSIDE_SRC}
  )
endif()

set_target_properties(phasar_ifdside
  PROPERTIES
  LINKER_LANGUAGE CXX
  PREFIX "lib"
)
