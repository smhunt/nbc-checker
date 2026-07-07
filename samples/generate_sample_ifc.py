"""Generate a minimal IFC4 model with a stair flight to smoke-test extraction."""
import ifcopenshell
import ifcopenshell.api.root, ifcopenshell.api.unit, ifcopenshell.api.context, ifcopenshell.api.project, ifcopenshell.api.aggregate

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

space = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSpace", name="LIV-01")
space.LongName = "Living Room"

f.write("samples/smoke_test.ifc")
print("Wrote samples/smoke_test.ifc")
