"""Generate a minimal IFC4 model with stair flights, a space and a window
to smoke-test extraction (attribute, pset, Qto and derived-value paths)."""
import ifcopenshell
import ifcopenshell.api.root, ifcopenshell.api.unit, ifcopenshell.api.context, ifcopenshell.api.project, ifcopenshell.api.aggregate
import ifcopenshell.api.pset

f = ifcopenshell.api.project.create_file(version="IFC4")
project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Smoke Test Dwelling")
ifcopenshell.api.unit.assign_unit(f)  # SI metres
site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Site")
building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="House")
storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="Ground Floor")
ifcopenshell.api.aggregate.assign_object(f, products=[site], relating_object=project)
ifcopenshell.api.aggregate.assign_object(f, products=[building], relating_object=site)
ifcopenshell.api.aggregate.assign_object(f, products=[storey], relating_object=building)

flight = ifcopenshell.api.root.create_entity(f, ifc_class="IfcStairFlight", name="Main Stair Flight")
flight.RiserHeight = 185.0   # mm (model default units are mm) - compliant
flight.TreadLength = 250.0   # mm - VIOLATION: < 255
flight.NumberOfRisers = 14

# Second flight: NO RiserHeight attribute — only NumberOfRisers plus a
# Qto_StairFlightBaseQuantities Height, so the extractor must DERIVE the riser
# (Height / NumberOfRisers = 2800 / 16 = 175 mm, compliant).
flight2 = ifcopenshell.api.root.create_entity(f, ifc_class="IfcStairFlight", name="Basement Stair Flight")
flight2.NumberOfRisers = 16
qto = ifcopenshell.api.pset.add_qto(f, product=flight2, name="Qto_StairFlightBaseQuantities")
ifcopenshell.api.pset.edit_qto(f, qto=qto, properties={"Height": 2800.0, "TreadLength": 260.0})

space = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSpace", name="LIV-01")
space.LongName = "Living Room"
# Ceiling height comes from a property set (pset path, not attribute/Qto).
pset = ifcopenshell.api.pset.add_pset(f, product=space, name="Pset_SpaceDimensions")
ifcopenshell.api.pset.edit_pset(f, pset=pset, properties={"CeilingHeight": 2450.0})

window = ifcopenshell.api.root.create_entity(f, ifc_class="IfcWindow", name="Bedroom Window W-01")
window.OverallHeight = 1200.0  # mm
window.OverallWidth = 900.0    # mm

f.write("samples/smoke_test.ifc")
print("Wrote samples/smoke_test.ifc")
