from __future__ import division
import sys
import iotbx.pdb
import mmtbx.utils
from mmtbx import monomer_library
from scitbx.array_family import flex
from libtbx.utils import Sorry
import iotbx.phil
import mmtbx.refinement.real_space.expload_and_refine

master_phil = iotbx.phil.parse("""

  input_files {
    map_coeffs_file = None
      .type = path
      .help = File with map coefficients
      .short_caption = Map coefficients
      .style = bold file_type:hkl input_file process_hkl child:fobs:data_labels\
        child:space_group:space_group child:unit_cell:unit_cell

    map_coeffs_labels = None
      .type = str
      .input_size = 160
      .help = Optional label specifying which columns of of map coefficients \
          to use
      .short_caption = Map coeffs label
      .style = bold renderer:draw_fobs_label_widget

    map_file = None
      .type = path
      .help = File with CCP4-style map
      .short_caption = Map file

    pdb_in = None
      .type = path
      .help = Input PDB file to minimize
      .short_caption = Input PDB file

  }
  output_files {

    pdb_out = None
      .type = path
      .help = Output PDB file with CA positions
      .short_caption = Output PDB file

    prefix = tst_00
      .type = str
      .help = Prefix for output files
      .short_caption = Prefix for output files
  }
  crystal_info {
     resolution = None
       .type = float
       .help = High-resolution limit. Data will be truncated at this\
               resolution. If a map is supplied, it will be Fourier \
               filtered at this resolution. Required if input is a map and \
                only_original_map is not set.
       .short_caption = High-resolution limit
       .style = resolution
     space_group = None
       .type = space_group
       .short_caption = Space Group
       .help = Space group (normally read from the data file)
     unit_cell = None
       .type = unit_cell
       .short_caption = Unit Cell
       .help = Unit Cell (normally read from the data file)
  }
  minimization {
     strategy = *ca_only all_atoms
       .type = choice
       .help = Ignored for now. \
          Strategy.  CA_only uses just CA atoms, all_atoms uses all
       .short_caption = CA only or all atoms

     number_of_build_cycles = 4
       .type = int
       .short_caption = Build cycles
       .help = Number of build cycles \
           (each build cycle has several macro_cycles)

     number_of_macro_cycles = 5
       .type = int
       .short_caption = Number of overall cycles of minimization
       .help = Number of overall (macro) cycles of minimization

     target_bond_rmsd = 0.02
       .type = float
       .short_caption = Target bond rmsd
       .help = Target bond rmsd

     target_angle_rmsd = 2.0
       .type = float
       .short_caption = Target angle RMSD
       .help = Target angle RMSD

     number_of_trials = 5
       .type = int
       .short_caption = Number of trials
       .help = Number of trials

     start_xyz_error = 10.0
       .type = float
       .short_caption = Starting coordinate error
       .help = Starting coordinate error

  }
  control {
      verbose = False
        .type = bool
        .help = Verbose output
        .short_caption = Verbose output
      random_seed = None
        .type = int
        .short_caption = Random seed
        .help = Random seed. If set, the same result will be found each time.
  }
""", process_includes=True)
master_params = master_phil

def get_params(args,out=sys.stdout):
  command_line = iotbx.phil.process_command_line_with_files(
    reflection_file_def="input_files.map_coeffs_file",
    map_file_def="input_files.map_file",
    pdb_file_def="input_files.pdb_in",
    args=args,
    master_phil=master_phil)
  params = command_line.work.extract()
  print >>out,"\nMinimize_ca ... optimize a coarse-grain model in EM or low-resolution X-ray map"
  master_phil.format(python_object=params).show(out=out)
  return params

def get_params_edits(n_ca=None,edit_file_name='bond_edits.eff',out=sys.stdout):

  from mmtbx.monomer_library.pdb_interpretation import geometry_restraints_edits_str
  edit_phil = iotbx.phil.parse(
  """refinement.geometry_restraints.edits
      { %s }
  """ %geometry_restraints_edits_str
  )
  # Generate restraint file
  f=open(edit_file_name,'w')
  print >>f,"""
  refinement.geometry_restraints.edits {
    excessive_bond_distance_limit = 10
  """

  for i in xrange(1,n_ca+1):
    if i+1 <=n_ca:
     print >>f,"""
      bond {

      action = *add delete change
      atom_selection_1 = chain E and resseq %d  and name CA
      atom_selection_2 = chain E and resseq %d and name CA
      distance_ideal = 3.8
      sigma = 0.5
      slack = None
      symmetry_operation = None
      }
    """ %(i,i+1)

    if i+2 <=n_ca:
     print >>f,"""
      bond {

      action = *add delete change
      atom_selection_1 = chain E and resseq %d  and name CA
      atom_selection_2 = chain E and resseq %d and name CA
      distance_ideal = 5.5
      sigma = 0.5
      slack = None
      symmetry_operation = None
      }
    """ %(i,i+2)

  print >>f,"""
    }
  """
  f.close()
  command_line = iotbx.phil.process_command_line_with_files(
      args=[edit_file_name],master_phil=edit_phil)
  params = command_line.work.extract()
  edit_phil.format(python_object=params).show(out=out)
  return params.refinement.geometry_restraints.edits

def ccp4_map(crystal_symmetry, file_name, map_data):
  from iotbx import ccp4_map
  ccp4_map.write_ccp4_map(
      file_name=file_name,
      unit_cell=crystal_symmetry.unit_cell(),
      space_group=crystal_symmetry.space_group(),
      #gridding_first=(0,0,0),# This causes a bug (map gets shifted)
      #gridding_last=n_real,  # This causes a bug (map gets shifted)
      map_data=map_data,
      labels=flex.std_string([""]))

def get_map_coeffs(
        map_coeffs_file=None,
        map_coeffs_labels=None):
  from iotbx import reflection_file_reader
  reflection_file=reflection_file_reader.any_reflection_file(map_coeffs_file)
  miller_arrays=reflection_file.as_miller_arrays()
  for ma in miller_arrays:
    if not ma.is_complex_array: continue
    if not map_coeffs_labels or map_coeffs_labels==ma.info().labels[0]:
      return ma
  raise Sorry("Unable to find map coeffs in the file %s with labels %s" %(
      map_coeffs_file,str(map_coeffs_labels)))

def run_one_cycle(
    params=None,
    map_data=None,
    map_coeffs=None,
    pdb_inp=None,
    pdb_string=None,
    crystal_symmetry=None,
    params_edits=None,
    out=sys.stdout):


  hierarchy=pdb_inp.construct_hierarchy()
  hierarchy.atoms().reset_i_seq()
  xrs=pdb_inp.xray_structure_simple()
  if not pdb_string:
    pdb_string=hierarchy.as_pdb_string()
  #
  asc = hierarchy.atom_selection_cache()
  sel_ca    = asc.selection(string="name CA")
  sel_other = ~sel_ca
  #

  # Initialize states accumulator
  states = mmtbx.utils.states(pdb_hierarchy=hierarchy, xray_structure=xrs)
  states.add(sites_cart = xrs.sites_cart())

  # Build geometry restraints
  pi_params = monomer_library.pdb_interpretation.master_params
  pi_params = pi_params.extract()
  pi_params.max_reasonable_bond_distance=500
  pi_params.nonbonded_weight=2000
  #pi_params.peptide_link.ramachandran_restraints=True
  #pi_params.peptide_link.rama_potential="emsley"
  if 0:
    pi_params.nonbonded_distance_cutoff=10
    pi_params.vdw_1_4_factor=2.0
  processed_pdb_file = monomer_library.pdb_interpretation.process(
    mon_lib_srv              = monomer_library.server.server(),
    ener_lib                 = monomer_library.server.ener_lib(),
    params                   = pi_params,
    raw_records              = pdb_string,
    strict_conflict_handling = True,
    force_symmetry           = True,
    log                      = None)
  geometry = processed_pdb_file.geometry_restraints_manager(
    show_energies                = False,
    plain_pairs_radius           = 5,
    params_edits = params_edits,
    assume_hydrogens_all_missing = True)
  restraints_manager = mmtbx.restraints.manager(
    geometry      = geometry,
    normalization = True)

  if params.control.verbose:
    geometry.write_geo_file()

  ear = mmtbx.refinement.real_space.expload_and_refine.run(
    xray_structure          = xrs,
    pdb_hierarchy           = hierarchy,
    map_data                = map_data,
    restraints_manager      = restraints_manager,
    number_of_macro_cycles  = params.minimization.number_of_macro_cycles,
    target_bond_rmsd        = params.minimization.target_bond_rmsd,
    target_angle_rmsd       = params.minimization.target_angle_rmsd,
    number_of_trials        = params.minimization.number_of_trials,
    xyz_shake               = params.minimization.start_xyz_error,
    states                  = states)

  return ear.pdb_hierarchy, ear.xray_structure, ear.states, ear.scorer.target

def run(args,
    map_data=None,
    map_coeffs=None,
    pdb_inp=None,
    pdb_string=None,
    crystal_symmetry=None,
    params_edits=None,
    out=sys.stdout):

  # Get the parameters
  params=get_params(args=args,out=out)

  if params.control.random_seed:
    flex.set_random_seed(params.control.random_seed)
    print >>out,"\nUsing random seed of %d" %(params.control.random_seed)

  # Get map_data if not present
  if not map_data:
    if not map_coeffs:
      map_coeffs=get_map_coeffs(
        map_coeffs_file=params.input_files.map_coeffs_file,
        map_coeffs_labels=params.input_files.map_coeffs_labels)
    if not map_coeffs:
      raise Sorry("Need map_coeffs_file")

    fft_map = map_coeffs.fft_map(resolution_factor = 0.25)
    fft_map.apply_sigma_scaling()
    map_data = fft_map.real_map_unpadded()
  if map_coeffs and not crystal_symmetry:
    crystal_symmetry=map_coeffs.crystal_symmetry()

  assert crystal_symmetry is not None

  # Get the starting model
  if pdb_inp is None:
    if not pdb_string:
      if params.input_files.pdb_in:
        pdb_string=open(params.input_files.pdb_in).read()
      else:
        raise Sorry("Need an input PDB file")
    pdb_inp=iotbx.pdb.input(source_info=None, lines = pdb_string)

  best_score=None
  best_result=[]
  for cycle in xrange(1,max(2,params.minimization.number_of_build_cycles+1)):
    # and run one cycle
    print >>out,"\nCycle %d of building " %(cycle)
    pdb_hierarchy,xray_structure,states,score=run_one_cycle(
      params=params,
      map_data=map_data,
      pdb_inp=pdb_inp,
      pdb_string=pdb_string,
      crystal_symmetry=crystal_symmetry,
      params_edits=params_edits,
      out=out)
    if best_score is None or score > best_score:
      best_score=score
      best_result=[pdb_hierarchy,xray_structure,states,score]
      print >>out,"Best score so far is: %7.2f" %(best_score)
      # get new pdb string
      from cStringIO import StringIO
      f=StringIO()
      if crystal_symmetry:
        print >>f, iotbx.pdb.format_cryst1_record(
           crystal_symmetry=crystal_symmetry)
      print >>f, pdb_hierarchy.as_pdb_string()
      pdb_string=f.getvalue()

    # Redo pdb_inp as we are going to get the hierarchy later
    pdb_inp=iotbx.pdb.input(source_info=None, lines = pdb_string)

    if params.output_files.pdb_out:
      f=open(params.output_files.pdb_out,'w')
      print >>f, pdb_string
      f.close()
    return best_result

if   (__name__ == "__main__"):
  args=sys.argv[1:]
  run(args=args)