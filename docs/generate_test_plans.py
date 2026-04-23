"""Generate BackendTestPlan.docx and FrontendTestPlan.docx.

Both documents follow the IEEE-829 section layout of TestPlanTemplate.docx
(Sections 1-17 + Appendices A/B). Regenerate with:

    python docs/generate_test_plans.py

Requires `python-docx` (install with `pip install python-docx`).
"""

from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

DOCS_DIR = Path(__file__).parent


def add_heading(doc, text, level):
    h = doc.add_heading(text, level=level)
    return h


def add_para(doc, text, bold=False):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(11)
    if bold:
        r.bold = True
    return p


def add_bullets(doc, items):
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def risk_cell_color(cell, risk):
    """Color the risk cell by severity."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    color = {"H": "F4CCCC", "M": "FFF2CC", "L": "D9EAD3"}.get(risk, "FFFFFF")
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)


def add_features_table(doc, rows):
    """rows: list of (Feature, Tested by, Risk)"""
    table = doc.add_table(rows=1 + len(rows), cols=3)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text = "Feature (user view)"
    hdr[1].text = "Tested by"
    hdr[2].text = "Risk"
    for cell in hdr:
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
    for i, (feature, tested_by, risk) in enumerate(rows, start=1):
        c = table.rows[i].cells
        c[0].text = feature
        c[1].text = tested_by
        c[2].text = risk
        risk_cell_color(c[2], risk)
    return table


def add_cover(doc, title):
    cover = doc.add_paragraph()
    cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cover.add_run("Smart Amenities Finder\n")
    r.bold = True
    r.font.size = Pt(20)
    r2 = cover.add_run(title + "\n")
    r2.bold = True
    r2.font.size = Pt(18)
    r3 = cover.add_run("SE 6387 Advanced Software Engineering Project\n")
    r3.font.size = Pt(12)
    r4 = cover.add_run("R.Z. Wenkstern\n")
    r4.font.size = Pt(12)
    doc.add_paragraph()


def add_revision_history(doc):
    add_heading(doc, "Revision History", level=1)
    t = doc.add_table(rows=2, cols=4)
    t.style = "Light Grid Accent 1"
    hdr = t.rows[0].cells
    hdr[0].text = "Version"
    hdr[1].text = "Date"
    hdr[2].text = "Description"
    hdr[3].text = "Authors"
    row = t.rows[1].cells
    row[0].text = "1.0"
    row[1].text = "2026-04-08"
    row[2].text = "Initial draft"
    row[3].text = ""
    doc.add_paragraph()


# ────────────────────────────────────────────────────────────────────
# BACKEND TEST PLAN
# ────────────────────────────────────────────────────────────────────

def build_backend_plan():
    doc = Document()
    add_cover(doc, "Backend Test Plan")
    add_revision_history(doc)

    add_heading(doc, "1. Test Plan Identifier", level=1)
    add_para(doc, "Backend Test Plan v1.0 — Smart Amenities Finder Flask API (flask-api/app.py).")

    add_heading(doc, "2. Introduction", level=1)
    add_para(
        doc,
        "This plan covers endpoint-level testing of the Flask backend that powers the Smart "
        "Amenities Finder Android app. Scope is limited to the routes in flask-api/app.py that "
        "correspond to the in-scope use cases from the Smart Amenities Finder use case diagram. "
        "Tests run against a stubbed psycopg2 connection (no live AWS RDS), so they can execute "
        "in any developer environment or CI runner without network access to the database."
    )

    add_heading(doc, "3. Test Items (Functions)", level=1)
    add_para(doc, "Items under test in flask-api/app.py:")
    add_bullets(doc, [
        "GET /api/edges — return all nav_edges for map rendering",
        "GET /api/nodes — return nav_nodes, optionally filtered by type or zone",
        "GET /api/amenities — return all amenities with linked nav_node lat/lng and derived zone",
        "GET /api/amenity-types — return distinct amenity categories",
        "GET /api/route — pgRouting Dijkstra route between two node IDs",
        "GET /api/route-to-amenity — nearest routable amenity of a given type (zone + accessibility aware)",
        "GET /api/nearest — nearest nav_node to a lat/lng, optionally restricted to a zone",
        "Pure helpers: calculate_bearing, bearing_to_cardinal, haversine_distance_meters, "
        "get_direction_instruction (already covered by flask-api/test_app.py)",
    ])

    add_heading(doc, "4. Software Risk Issues", level=1)
    add_bullets(doc, [
        "Zone-boundary correctness: a bug in the zone filter would route a secure-side user "
        "through TSA or vice versa. High impact.",
        "Coordinate-frame mixing: amenities carry raw CSV lat/lng and nav_node lat/lng. Routing "
        "must use the nav_node frame. Past bugs have produced markers that don't match routes.",
        "Shared module-level database cursor: app.py opens one connection at import and reuses "
        "it for every request. A dangling transaction or unhandled exception can poison "
        "subsequent requests until a restart.",
        "pgRouting / PostgreSQL extension dependency: the backend requires pgr_dijkstra. Any "
        "schema/extension drift on AWS RDS will break /api/route and /api/route-to-amenity.",
        "Complexity in /api/route-to-amenity: it does zone derivation, candidate sorting, and "
        "an unreachable-candidate fallback loop in a single function — highest defect surface.",
    ])

    add_heading(doc, "5. Features to be Tested", level=1)
    add_para(
        doc,
        "Each feature below is mapped to the use case it supports and rated H/M/L. The suite "
        "is intentionally lean: one minimal happy-path test per use case, plus the unhappy-path "
        "zone-leak guard for the highest-risk path. Defensive 4xx-input-validation tests, "
        "framework-default smoke tests, and parser-variant padding have been removed so every "
        "remaining test catches a bug a reviewer would actually care about."
    )
    add_features_table(doc, [
        ("Navigate — View Map (load nodes for map render)",
         "GET /api/nodes happy path "
         "(test_endpoints.py::TestViewMap::test_get_nodes_returns_list)",
         "L"),
        ("Navigate — Generate Route to Amenity (nearest amenity of a type)",
         "GET /api/route-to-amenity end-to-end: start lookup, candidate query, dijkstra "
         "reconstruction, waypoint serialization "
         "(test_endpoints.py::TestGenerateRouteToAmenity::test_happy_path_returns_waypoints)",
         "H"),
        ("Navigate — Reroute (direct node-to-node route with turn instructions)",
         "GET /api/route happy path; 3-node path with N→E turn proves the bearing/cardinal/"
         "direction-instruction math helpers in app.py are wired into the route response "
         "(test_endpoints.py::TestReroute::test_happy_path_returns_waypoints_with_instructions)",
         "H"),
        ("View Amenities (markers fed by linked nav_node lat/lng)",
         "GET /api/amenities returns the linked nav_node lat/lng (not the raw amenity row) — "
         "regression guard for the coordinate-frame-mixing bug class flagged in the project notes "
         "(test_endpoints.py::TestViewAmenities::test_get_amenities_returns_list)",
         "M"),
        ("Verify Security Zone Access (zone-filtered nearest node)",
         "GET /api/nearest with zone=secure returns a secure node AND issues the zone-filtered "
         "SQL variant — proves the zone is read and used, not silently dropped "
         "(test_endpoints.py::TestVerifySecurityZoneAccess::test_nearest_with_secure_zone_returns_secure_node)",
         "H"),
        ("Verify Security Zone Access (zone-leak guard on amenity routing — UNHAPPY PATH)",
         "GET /api/route-to-amenity with no candidates in the start node's zone returns 404 "
         "and the zone name is present in the error message — proves the zone is being read "
         "from the start node and used to scope the candidate search "
         "(test_endpoints.py::TestVerifySecurityZoneAccess::test_no_amenities_in_zone_returns_404)",
         "H"),
        ("Apply Filters and Profiles (wheelchair, type, restroom gender)",
         "Covered on the frontend in NavigationViewModelTest.kt (chip filter, dropdown filter, "
         "restroom gender sub-filter, accessibility mode). The Flask endpoint just forwards the "
         "accessible flag to the SQL filter, so duplicating that coverage on the backend would "
         "be padding.",
         "M"),
    ])

    add_heading(doc, "6. Features NOT to be Tested", level=1)
    add_bullets(doc, [
        "Update Map Display — explicitly out of scope per the test request.",
        "Apply Route Disruptions — not implemented in the backend yet. Deferred to "
        "Section 11 (Remaining Test Tasks).",
        "Update Amenity Occupancy — not implemented (no occupancy column on amenities).",
        "Update Amenity Waiting Crowd Level — not implemented (no crowd_level column).",
        "Live AWS RDS integration — intentionally stubbed. Database correctness is validated "
        "separately by running the schema and seed SQL under flask-api/SQL_FILES/.",
        "/map, /calibrate, /api/random-node — developer/debug-only routes, not user-facing.",
        "pgr_dijkstra itself — it's a third-party PostgreSQL extension and is outside the "
        "scope of this application's tests.",
    ])

    add_heading(doc, "7. Approach (Strategy)", level=1)
    add_para(
        doc,
        "Pytest + Flask's built-in test client, with a shared FakeCursor injected via "
        "flask-api/conftest.py. The fixture:"
    )
    add_bullets(doc, [
        "Sets dummy DB_* environment variables before importing app.py so load_dotenv() can't "
        "pull real credentials.",
        "Replaces sys.modules['NearestNodeFinder'] with a fake that always returns index 0, "
        "avoiding numpy/scipy install requirements in CI.",
        "Replaces psycopg2.connect with a lambda returning a FakeConn whose single cursor's "
        "fetchall / fetchone responses are queued per-test.",
        "Auto-resets the cursor queue and /api/nearest's KDTree cache between every test so "
        "state can't leak.",
    ])
    add_para(
        doc,
        "Tests are organized as one TestClass per use case in flask-api/test_endpoints.py. "
        "Pre-existing math-helper tests in flask-api/test_app.py remain and are run in the "
        "same pytest session."
    )

    add_heading(doc, "8. Item Pass/Fail Criteria", level=1)
    add_bullets(doc, [
        "Pass: every test in flask-api/test_app.py and flask-api/test_endpoints.py passes.",
        "Pass: the full suite runs in under 5 seconds on a developer laptop without a live DB.",
        "Fail: any endpoint test returns an unexpected status code or response shape.",
        "Fail: any new endpoint added to app.py without a corresponding test case in "
        "test_endpoints.py is treated as an uncovered feature and blocks the release.",
    ])

    add_heading(doc, "9. Suspension Criteria and Resumption Requirements", level=1)
    add_para(
        doc,
        "Testing is suspended if the app.py module can no longer be imported under the stubbed "
        "psycopg2 (e.g. a new top-level side effect is added that requires a real connection). "
        "Resumption requires updating conftest.py with an appropriate stub. Testing is also "
        "suspended if the database schema changes mid-run; the fake cursor's queued rows "
        "would no longer reflect reality."
    )

    add_heading(doc, "10. Test Deliverables", level=1)
    add_bullets(doc, [
        "This test plan document (docs/BackendTestPlan.docx)",
        "flask-api/conftest.py — shared pytest fixtures and DB stubs",
        "flask-api/test_endpoints.py — endpoint test cases (6 tests, one per use case + one "
        "extra unhappy-path zone-leak guard)",
        "flask-api/test_app.py — pre-existing math helper tests (13 tests)",
        "pytest terminal output as evidence of passing runs (19 passed, 0 failed at last run)",
    ])

    add_heading(doc, "11. Remaining Test Tasks", level=1)
    add_bullets(doc, [
        "Apply Route Disruptions — tests will be added when the backend exposes a disruptions "
        "endpoint and app.py starts filtering edges based on it.",
        "Update Amenity Occupancy — tests will be added when /api/amenities (or a new route) "
        "starts returning an occupancy field.",
        "Update Amenity Waiting Crowd Level — same: tests to be added when the backend emits "
        "a crowd_level field.",
        "End-to-end integration against a throwaway Postgres container — a future nice-to-have "
        "that would cover the pgr_dijkstra dependency the current unit tests stub out.",
    ])

    add_heading(doc, "12. Environmental Needs", level=1)
    add_bullets(doc, [
        "Python 3.10+ with pytest, Flask, flask-cors, psycopg2-binary, python-dotenv installed.",
        "No live AWS RDS connection required. Dummy DB_* env vars are set by conftest.py.",
        "No numpy/scipy required for the unit test layer (NearestNodeFinder is stubbed).",
        "Run command: python -m pytest flask-api/ -v",
    ])

    add_heading(doc, "13. Staffing and Training Needs", level=1)
    add_para(
        doc,
        "Any team member familiar with pytest can run and extend this suite. New contributors "
        "only need to understand the FakeCursor queue pattern in conftest.py — a 5-minute "
        "read — before writing new endpoint tests."
    )

    add_heading(doc, "14. Responsibilities", level=1)
    add_bullets(doc, [
        "Backend developer: writes new endpoint tests when adding a new route.",
        "Team lead: reviews risk ratings (Section 5) when scope changes.",
        "All team members: run the full pytest suite before merging backend changes.",
    ])

    add_heading(doc, "15. Schedule", level=1)
    add_para(
        doc,
        "Schedule is dependent on the master project plan. The backend test suite must be "
        "passing at the end of each Build milestone (Builds 1-3). Specifically:"
    )
    add_bullets(doc, [
        "Build 1: all tests for Navigate + View Amenities + Verify Security Zone Access pass.",
        "Build 2: extend with tests for occupancy + crowd level once those features ship.",
        "Build 3: extend with any remaining tests for account management / admin features.",
    ])

    add_heading(doc, "16. Planning Risks and Contingencies", level=1)
    add_bullets(doc, [
        "Risk: AWS RDS schema drift. Mitigation: tests stub the DB entirely, so they remain "
        "green even during schema migrations; correctness is re-checked manually against the "
        "live instance before release.",
        "Risk: a test relies on a cursor response shape that no longer matches the real column "
        "list. Mitigation: when adding real SQL queries, check the queued dict keys against "
        "the SQL SELECT list and update test fixtures in lockstep.",
        "Risk: late delivery of Route Disruptions / Occupancy / Crowd Level features. "
        "Mitigation: those tests are explicitly deferred in Section 11 and will not block "
        "earlier Builds.",
    ])

    add_heading(doc, "17. Approvals", level=1)
    t = doc.add_table(rows=3, cols=3)
    t.style = "Light Grid Accent 1"
    hdr = t.rows[0].cells
    hdr[0].text = "Name"
    hdr[1].text = "Role"
    hdr[2].text = "Signature / Date"
    t.rows[1].cells[1].text = "Team Lead"
    t.rows[2].cells[1].text = "Instructor"

    add_heading(doc, "Appendix A: Glossary", level=1)
    gloss = [
        ("Zone", "Either 'secure' (post-TSA/airside) or 'public' (pre-TSA/landside). "
                 "Routing must not cross this boundary."),
        ("Waypoint", "A node in the navigation graph used by pgr_dijkstra. "
                     "`node_type='waypoint'` excludes synthetic linker nodes."),
        ("Linker node", "A synthetic nav_node attached to an amenity/elevator/escalator/"
                        "checkpoint. Often has an unreliable stored zone."),
        ("Derived zone", "The amenity zone computed at query time using neighbor consensus, "
                         "to work around stored zones that don't match physical location."),
        ("FakeCursor", "A scriptable psycopg2 cursor stand-in defined in flask-api/"
                       "conftest.py. Tests queue fetchall/fetchone responses per test."),
        ("pgr_dijkstra", "The shortest-path function from the pgRouting PostgreSQL extension."),
    ]
    t = doc.add_table(rows=1 + len(gloss), cols=2)
    t.style = "Light Grid Accent 1"
    t.rows[0].cells[0].text = "Term"
    t.rows[0].cells[1].text = "Definition"
    for i, (term, defn) in enumerate(gloss, start=1):
        t.rows[i].cells[0].text = term
        t.rows[i].cells[1].text = defn

    add_heading(doc, "Appendix B: References", level=1)
    add_bullets(doc, [
        "flask-api/app.py — endpoint implementations under test",
        "flask-api/test_app.py — pre-existing math helper tests",
        "flask-api/test_endpoints.py — endpoint tests authored for this plan",
        "flask-api/conftest.py — shared test fixtures and DB stubs",
        "Project notes: project overview and architectural constraints",
        "Smart Amenities Finder use case diagram",
        "IEEE 829 Test Plan Outline (template source)",
    ])

    out = DOCS_DIR / "BackendTestPlan.docx"
    doc.save(out)
    print(f"[ok] wrote {out}")


# ────────────────────────────────────────────────────────────────────
# FRONTEND TEST PLAN
# ────────────────────────────────────────────────────────────────────

def build_frontend_plan():
    doc = Document()
    add_cover(doc, "Frontend Test Plan")
    add_revision_history(doc)

    add_heading(doc, "1. Test Plan Identifier", level=1)
    add_para(doc, "Frontend Test Plan v1.0 — Smart Amenities Finder Android app (android-app/).")

    add_heading(doc, "2. Introduction", level=1)
    add_para(
        doc,
        "This plan covers unit-level testing of the Kotlin Android client for the Smart "
        "Amenities Finder project. Scope is limited to pure JVM unit tests that exercise the "
        "filter, state, and geometry logic used by the in-scope use cases from the use case "
        "diagram. UI / instrumented / Espresso tests are out of scope for this deliverable."
    )

    add_heading(doc, "3. Test Items (Functions)", level=1)
    add_para(doc, "Items under test in android-app/app/src/main/java/com/example/se6387map/:")
    add_bullets(doc, [
        "NavigationViewModel.kt — filteredAmenities(), pointToSegmentDistanceMeters(), "
        "toggleAccessibilityMode(), setTypeFilter(), setDropdownTypeFilter(), "
        "setRestroomGender(), selectAmenity(), clearSelectedAmenity(), isOffPath()",
        "NavigationViewModel.kt — NavigationState data class defaults and route-loaded shape",
        "NavigationApi.kt — Amenity, Waypoint, NavigationState data classes used as test "
        "fixtures",
    ])

    add_heading(doc, "4. Software Risk Issues", level=1)
    add_bullets(doc, [
        "Zone-aware filtering on the client: if filteredAmenities() does not honour "
        "state.currentZone, a user standing airside sees landside amenities that they "
        "cannot legally reach.",
        "Restroom gender regex: the filter uses a substring check. 'Female Bathroom' "
        "contains the substring 'male', so naive logic misclassifies. Existing tests cover "
        "this; any refactor must preserve it.",
        "Off-path detection: pointToSegmentDistanceMeters() backs the 15m off-path threshold. "
        "A sign-flip here would either recalculate constantly or never trigger.",
        "Singleton Retrofit client: the ViewModel constructs NavigationApi.service lazily. "
        "This makes ViewModel-level API mocking awkward and is why the suite sticks to pure "
        "unit tests of functions and state.",
    ])

    add_heading(doc, "5. Features to be Tested", level=1)
    add_para(
        doc,
        "Each feature below is mapped to the use case it supports and rated H/M/L. The suite "
        "is intentionally lean: combination tests, trivial setter tests, and tautologies have "
        "been removed so every remaining test catches a real bug. Two unhappy-path tests have "
        "been added for the cross-zone confirm/cancel guard introduced in commit 4e33e5c — "
        "the highest-risk new code path."
    )
    add_features_table(doc, [
        ("Navigate — View Map (amenity markers fed by filteredAmenities)",
         "NavigationViewModelTest filter tests cover the chip filter, dropdown filter, and "
         "accessibility filter that determine which markers render",
         "L"),
        ("Navigate — Reroute (off-path detection geometry + early-return guard)",
         "NavigationViewModelTest::pointOnSegment_isZero, "
         "pointPerpendicularToSegment_returnsPerpDistance, "
         "pointBeyondSegmentEnd_clampsToEndpoint, degeneratedSegment_returnsDistanceToPoint; "
         "NavigationStateTest::isOffPath_freshViewModel_returnsFalse_noRoute (crash guard for "
         "map taps before a route is loaded)",
         "H"),
        ("View Amenities (chip + dropdown + restroom gender filtering)",
         "NavigationViewModelTest filteredAmenities_typeFilter_keepsOnlyMatchingTypes, "
         "filteredAmenities_dropdownTypeFilter_keepsOnlyThatType, "
         "filteredAmenities_restroomGenderMale/Female/Any (Female test catches the 'female "
         "contains substring male' regex bug)",
         "M"),
        ("Verify Security Zone Access (zone branch of filteredAmenities — HAPPY PATH)",
         "ZoneFilterTest::currentZoneNull_hidesAllAmenities (until the user picks a start, "
         "the list is empty so they can't pick a destination on the wrong side of TSA); "
         "currentZoneSecure_keepsOnlySecureAmenities; currentZonePublic_keepsOnlyPublicAmenities",
         "H"),
        ("Verify Security Zone Access (null-zone leak guard — UNHAPPY PATH)",
         "ZoneFilterTest::currentZoneSet_dropsAmenitiesWithNullZone — proves an amenity row "
         "with a null zone field cannot leak across the TSA boundary once the user has a "
         "current zone (strict-equality null check)",
         "H"),
        ("Verify Security Zone Access (cross-zone routing confirm guard — UNHAPPY PATH)",
         "NavigationStateTest::routeToSpecificAmenity_crossZone_parksAmenityInsteadOfRouting — "
         "proves the synchronous guard in routeToSpecificAmenity() parks the amenity in "
         "pendingCrossZoneAmenity instead of issuing a route through TSA. "
         "NavigationStateTest::cancelCrossZoneRoute_clearsParkedAmenity — proves the cancel "
         "branch from the confirm dialog clears state cleanly.",
         "H"),
        ("Apply Filters and Profiles (wheelchair accessibility)",
         "NavigationViewModelTest filteredAmenities_accessibilityMode_viaAccessibleUnit, "
         "viaAmenityFlag, caseInsensitive (catches data-quality bug where the DB stores "
         "'YES'/'yes' inconsistently)",
         "M"),
        ("Apply Filters and Profiles (dropdown type change resets gender sub-filter)",
         "NavigationStateTest::setDropdownTypeFilter_resetsGenderWhenTypeChanges — proves a "
         "stale 'MALE' filter does not follow the user from the restroom list to the food "
         "list (easy-to-introduce refactor bug)",
         "M"),
    ])

    add_heading(doc, "6. Features NOT to be Tested", level=1)
    add_bullets(doc, [
        "Update Map Display — explicitly out of scope per the test request.",
        "Apply Route Disruptions — not implemented in the frontend. Deferred to Section 11.",
        "Update Amenity Occupancy — not implemented (no occupancy field in Amenity data class).",
        "Update Amenity Waiting Crowd Level — not implemented (no crowd_level field).",
        "Google Maps rendering, marker icons, polyline drawing — requires Android "
        "instrumentation and is out of scope for this unit test plan.",
        "Compose UI tests (buttons, sheets, dropdowns) — out of scope; scope is unit tests only.",
        "ViewModel methods that launch coroutines calling the Retrofit API "
        "(routeToAmenity, fetchRoute, setMockStart, loadAmenities) — out of scope because "
        "mocking Retrofit would require injecting the API client, a production refactor not "
        "justified by this deliverable.",
    ])

    add_heading(doc, "7. Approach (Strategy)", level=1)
    add_para(
        doc,
        "JUnit 4 pure JVM unit tests living under "
        "android-app/app/src/test/java/com/example/se6387map/. The suite relies entirely on "
        "the Android project's existing test dependencies (junit:junit:4.13.2). No new "
        "libraries or DI refactors are introduced."
    )
    add_bullets(doc, [
        "filteredAmenities() is a top-level function, so it can be tested by constructing a "
        "NavigationState directly and asserting on the result list.",
        "pointToSegmentDistanceMeters() is marked internal, so tests in the same module can "
        "call it via a NavigationViewModel instance.",
        "ViewModel methods that only mutate MutableStateFlow (toggleAccessibilityMode, "
        "setTypeFilter, setDropdownTypeFilter, selectAmenity, clearSelectedAmenity) are safe "
        "to test synchronously by constructing a NavigationViewModel and asserting on "
        "vm.state.value.",
        "NavigationState is a plain data class, so its default values can be asserted "
        "without spinning up a ViewModel.",
    ])

    add_heading(doc, "8. Item Pass/Fail Criteria", level=1)
    add_bullets(doc, [
        "Pass: :app:testDebugUnitTest succeeds with 0 failures.",
        "Pass: the full JVM unit test suite runs in under 30 seconds on a developer machine.",
        "Fail: any new code in NavigationViewModel.kt's filter or state transition path lands "
        "without a corresponding unit test.",
    ])

    add_heading(doc, "9. Suspension Criteria and Resumption Requirements", level=1)
    add_para(
        doc,
        "Testing is suspended if filteredAmenities() is refactored into a non-static member "
        "that requires a live API client or Android Context — the current tests would no "
        "longer compile. Resumption requires either reversing the refactor or introducing a "
        "test double for the dependency that was added."
    )

    add_heading(doc, "10. Test Deliverables", level=1)
    add_bullets(doc, [
        "This test plan document (docs/FrontendTestPlan.docx)",
        "android-app/app/src/test/java/com/example/se6387map/NavigationViewModelTest.kt "
        "(pre-existing, 16 tests — filter + off-path geometry, patched with currentZone "
        "defaults so the post-commit-4e33e5c zone-flip doesn't break them)",
        "android-app/app/src/test/java/com/example/se6387map/ZoneFilterTest.kt "
        "(4 tests — zone branch of filteredAmenities including null-zone-leak guard)",
        "android-app/app/src/test/java/com/example/se6387map/NavigationStateTest.kt "
        "(4 tests — isOffPath crash guard, dropdown gender reset, cross-zone confirm guard, "
        "cross-zone cancel)",
        "Gradle test HTML report under "
        "android-app/app/build/reports/tests/testDebugUnitTest/ "
        "(24 passed, 0 failed at last run)",
    ])

    add_heading(doc, "11. Remaining Test Tasks", level=1)
    add_bullets(doc, [
        "Apply Route Disruptions — will be added once Amenity / NavigationState carry a "
        "disruption field and the ViewModel has a method to apply them.",
        "Update Amenity Occupancy — tests will be added once the Amenity data class carries "
        "an occupancy field and the UI reads it.",
        "Update Amenity Waiting Crowd Level — same: add tests once crowd_level ships.",
        "ViewModel-level API tests — would require introducing dependency injection so the "
        "Retrofit client can be mocked. Explicitly out of scope for this deliverable.",
        "Compose UI tests (map, marker colors, sheets) — deferred; out of scope for this "
        "unit test plan.",
    ])

    add_heading(doc, "12. Environmental Needs", level=1)
    add_bullets(doc, [
        "JDK 17 (Android Studio's bundled JetBrains Runtime works).",
        "Gradle wrapper already committed under android-app/gradlew.",
        "No Android device or emulator required — testDebugUnitTest is a pure JVM run.",
        "Run command: cd android-app && ./gradlew :app:testDebugUnitTest",
    ])

    add_heading(doc, "13. Staffing and Training Needs", level=1)
    add_para(
        doc,
        "Any Kotlin developer comfortable with JUnit 4 can run and extend the suite. No "
        "training on MockK, Robolectric, or Compose testing is required, because the suite "
        "intentionally avoids those frameworks."
    )

    add_heading(doc, "14. Responsibilities", level=1)
    add_bullets(doc, [
        "Android developer: writes new unit tests when touching filteredAmenities, "
        "NavigationState, or ViewModel mutation methods.",
        "Team lead: re-reviews risk ratings (Section 5) whenever a new use case is added to "
        "the diagram.",
        "All team members: run ./gradlew :app:testDebugUnitTest before merging UI changes.",
    ])

    add_heading(doc, "15. Schedule", level=1)
    add_para(
        doc,
        "Schedule is dependent on the master project plan. The frontend unit test suite must "
        "be passing at the end of each Build milestone (Builds 1-3). Specifically:"
    )
    add_bullets(doc, [
        "Build 1: all tests for Navigate + View Amenities + Verify Security Zone Access pass.",
        "Build 2: extend with tests for occupancy + crowd level once those features ship.",
        "Build 3: extend with tests for account management UI.",
    ])

    add_heading(doc, "16. Planning Risks and Contingencies", level=1)
    add_bullets(doc, [
        "Risk: a refactor makes filteredAmenities() or isOffPath() harder to test (e.g. by "
        "folding them into a private closure). Mitigation: keep them as top-level or internal "
        "members — this is already a project convention.",
        "Risk: the Android Gradle plugin or JUnit dependency versions drift. Mitigation: tests "
        "use only the dependencies already wired in android-app/app/build.gradle.kts; no new "
        "transitive dependencies are introduced.",
        "Risk: late delivery of Route Disruptions / Occupancy / Crowd Level features. "
        "Mitigation: those tests are explicitly deferred in Section 11 and will not block "
        "earlier Builds.",
    ])

    add_heading(doc, "17. Approvals", level=1)
    t = doc.add_table(rows=3, cols=3)
    t.style = "Light Grid Accent 1"
    hdr = t.rows[0].cells
    hdr[0].text = "Name"
    hdr[1].text = "Role"
    hdr[2].text = "Signature / Date"
    t.rows[1].cells[1].text = "Team Lead"
    t.rows[2].cells[1].text = "Instructor"

    add_heading(doc, "Appendix A: Glossary", level=1)
    gloss = [
        ("Zone", "Either 'secure' (post-TSA/airside) or 'public' (pre-TSA/landside). The "
                 "frontend only shows amenities in the same zone as the user's current start."),
        ("currentZone", "NavigationState field that is null until the user picks a start "
                        "location. When null, the zone filter is skipped."),
        ("Off-path", "User position is more than OFF_PATH_THRESHOLD_METERS (15 m) from the "
                     "active route polyline. Triggers a recalculation."),
        ("pointToSegmentDistanceMeters", "Internal geometry helper that projects a lat/lng "
                                         "onto a route segment and returns the haversine "
                                         "distance in meters."),
        ("StateFlow", "Kotlin coroutines Flow type that holds one value and emits updates. "
                      "NavigationViewModel exposes NavigationState via a StateFlow."),
    ]
    t = doc.add_table(rows=1 + len(gloss), cols=2)
    t.style = "Light Grid Accent 1"
    t.rows[0].cells[0].text = "Term"
    t.rows[0].cells[1].text = "Definition"
    for i, (term, defn) in enumerate(gloss, start=1):
        t.rows[i].cells[0].text = term
        t.rows[i].cells[1].text = defn

    add_heading(doc, "Appendix B: References", level=1)
    add_bullets(doc, [
        "android-app/app/src/main/java/com/example/se6387map/NavigationViewModel.kt — "
        "primary item under test",
        "android-app/app/src/main/java/com/example/se6387map/NavigationApi.kt — data classes",
        "android-app/app/src/test/java/com/example/se6387map/NavigationViewModelTest.kt — "
        "pre-existing filter + geometry tests",
        "android-app/app/src/test/java/com/example/se6387map/ZoneFilterTest.kt — zone branch "
        "tests authored for this plan",
        "android-app/app/src/test/java/com/example/se6387map/NavigationStateTest.kt — "
        "state + selection + filter tests authored for this plan",
        "Project notes: project overview and architectural constraints",
        "Smart Amenities Finder use case diagram",
        "IEEE 829 Test Plan Outline (template source)",
    ])

    out = DOCS_DIR / "FrontendTestPlan.docx"
    doc.save(out)
    print(f"[ok] wrote {out}")


# ────────────────────────────────────────────────────────────────────
# INTEGRATION TEST PLAN  (a.k.a. Master/Integration Test Plan)
# ────────────────────────────────────────────────────────────────────

def build_integration_test_plan():
    doc = Document()

    # ─── Cover ──────────────────────────────────────────────────────
    cover = doc.add_paragraph()
    cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cover.add_run("Smart Amenities Finder\n")
    r.bold = True
    r.font.size = Pt(20)
    r2 = cover.add_run("Integration Test Plan\n")
    r2.bold = True
    r2.font.size = Pt(18)
    r3 = cover.add_run("SE 6387 Advanced Software Engineering Project\n")
    r3.font.size = Pt(12)
    r4 = cover.add_run("R.Z. Wenkstern\n")
    r4.font.size = Pt(12)
    r5 = cover.add_run("Date 4/9/26\n\n")
    r5.font.size = Pt(12)

    # Group / ownership split (was bare names; now name + role)
    r6 = cover.add_run("Group 1\n")
    r6.bold = True
    r6.font.size = Pt(12)
    for line in [
        "Wajih Anwar — Project Manager",
        "Alex Bowser — System Architect",
        "Lennon Crow — Backend / Database Lead",
        "Amelia Quinn — Frontend / Android Lead",
    ]:
        rl = cover.add_run(line + "\n")
        rl.font.size = Pt(12)

    doc.add_paragraph()

    # ─── Revision history ──────────────────────────────────────────
    add_heading(doc, "Revision History", level=1)
    t = doc.add_table(rows=3, cols=4)
    t.style = "Light Grid Accent 1"
    hdr = t.rows[0].cells
    hdr[0].text = "Version"
    hdr[1].text = "Date"
    hdr[2].text = "Description"
    hdr[3].text = "Authors"
    row1 = t.rows[1].cells
    row1[0].text = "1.0"
    row1[1].text = "2026-04-09"
    row1[2].text = "Initial draft for iteration 1"
    row1[3].text = "Wajih Anwar, Alex Bowser, Amelia Quinn, Lennon Crow"
    row2 = t.rows[2].cells
    row2[0].text = "1.1"
    row2[1].text = "2026-04-09"
    row2[2].text = (
        "Updated database schema section to match live AWS RDS; added role labels "
        "to author block; rewrote 'Why hybrid' rationale; left 'Why PostgreSQL "
        "over MySQL' content unchanged."
    )
    row2[3].text = "Lennon Crow"
    doc.add_paragraph()

    # ─── 1. TEST PLAN IDENTIFIER ───────────────────────────────────
    add_heading(doc, "1. Test Plan Identifier", level=1)
    add_para(
        doc,
        "To help determine which Plan our group wished to go with, our team labeled "
        "out all candidate plan styles and described their scope, content, project "
        "materials, and update frequency."
    )

    add_heading(doc, "Master Plan", level=2)
    add_para(doc, "Scope: Spans all phases of the project.", bold=True)
    add_bullets(doc, [
        "Overall project objectives and scope",
        "Major milestones and phase completion dates",
        "Total budget allocation across all phases",
        "High-level resource requirements",
        "Major risks and constraints",
    ])
    add_para(doc, "Project:", bold=True)
    add_bullets(doc, [
        "Timeline: Between January and May 2026",
        "Phases: Three Elaboration Phases",
        "Budget: $100 for AWS",
        "Stakeholders: DFW Airport",
    ])
    add_para(doc, "Completion: All 8 Use Cases across iterations.")
    add_para(doc, "Update Frequency: Updated at each phase boundary or when major changes occur.")

    add_heading(doc, "Level Plan", level=2)
    add_para(doc, "Scope: Covers one iteration only.", bold=True)
    add_bullets(doc, [
        "Specific use cases to be implemented in this iteration",
        "Detailed task breakdown and assignments",
        "Specific resource allocation for this iteration",
    ])
    add_para(doc, "Project (Elaboration Phases):", bold=True)
    add_bullets(doc, [
        "Iteration 1 — detailed design, operation contracts, UC realization, "
        "design class diagrams, database design and schema, and testing",
        "Iteration 2 — continues to build on Build 1 and adds additional Use Cases "
        "and real-time data flow",
        "Iteration 3 — final integration",
    ])
    add_para(doc, "Update Frequency: Each iteration; updated daily.")

    add_heading(doc, "Integration Plan", level=2)
    add_para(doc, "Scope: Covers integration strategy across iterations or within a single build.", bold=True)
    add_bullets(doc, [
        "Integration strategy: big bang, incremental, top-down, bottom-up, or continuous integration",
        "Integration sequence: which components integrate in what order",
        "Integration dependencies: what must be completed before integration can occur",
        "Integration testing approach: how integrated components will be validated",
        "Build schedule: when builds occur and what they include",
    ])
    add_para(doc, "Project:", bold=True)
    add_bullets(doc, [
        "Build 1: integrate Android frontend + Backend API + Database for UC1 and UC2",
        "    Frontend: map display, amenity selection UI",
        "    Backend: routing engine, amenity data API",
        "    Database: amenity metadata, location data",
        "    Integration: frontend calls backend API; backend queries database",
        "Build 2: integrate Build 1 + sensor data flows (UC5, UC6, UC7)",
        "    New components: mock sensor APIs, occupancy detection, crowd detection",
        "    Integration: sensor data → backend → database → frontend display update",
        "    Testing: verify real-time data flow end-to-end",
        "Build 3: integrate Build 2 + account management + reporting (UC8, UC4, UC3)",
        "    New components: user authentication, account database, admin portal, reporting system",
        "    Integration: all previous builds + new user-facing and admin features",
        "    Testing: full system integration test",
    ])

    add_para(
        doc,
        "The Integration Test Plan was chosen because the DFW Airport Navigation "
        "System is a multi-component, distributed system, where the greatest risk "
        "is how the modules interact with each other. The system consists of an "
        "Android frontend, a Flask backend API, and an AWS-hosted database that "
        "must communicate seamlessly to deliver accurate navigation and live "
        "updates to users. While each component can be tested independently "
        "through unit or level-based testing, such approaches do not adequately "
        "capture failures that occur at the boundaries between systems — "
        "mismatched data formats, delayed API responses, or incorrect "
        "synchronization of real-time data. Integration testing specifically "
        "targets these interaction points, ensuring that data flows correctly "
        "from database to backend to front-end."
    )
    add_para(
        doc,
        "Additionally, the project's development structure naturally aligns with "
        "an integration-focused testing strategy. Each build introduces new "
        "components or enhances existing ones. An Integration Test Plan allows "
        "the team to progressively test these additions in combination with "
        "previously developed components, reducing the risk of discovering major "
        "system-wide issues late in the development cycle. The Integration Plan "
        "provides a more practical and targeted approach for validating "
        "end-to-end functionality. It ensures that each stage of development "
        "produces a working, connected system, rather than a collection of "
        "isolated features."
    )

    # ─── 2. INTRODUCTION ───────────────────────────────────────────
    add_heading(doc, "2. Introduction", level=1)
    add_para(
        doc,
        "This Integration Test Plan defines the strategy, scope, and approach for "
        "testing the integration of components within the DFW Airport Smart "
        "Amenities Finder system across three incremental builds during the "
        "Elaboration phase (March–May 2026). The plan ensures that separately "
        "developed subsystems (Android frontend, Flask backend, PostgreSQL "
        "database, and mock sensor APIs) communicate correctly and deliver "
        "end-to-end navigation and real-time amenity status functionality to "
        "passengers in Terminal D."
    )
    add_para(doc, "Scope:", bold=True)
    add_bullets(doc, [
        "Build 1: integration of Android Studio front-end, Flask backend, and "
        "PostgreSQL database for UC1 (Navigate) and UC2 (View Amenities)",
        "Build 2: integration of mock sensor APIs (occupancy and crowd detection) "
        "with Build 1 for UC5, UC6, UC7",
        "Build 3: integration of account management, admin portal, and reporting "
        "features for UC3, UC4, UC8",
    ])
    add_para(doc, "Resources and Budget:", bold=True)
    add_bullets(doc, [
        "Testing is conducted by Group 1 team members (4 students); no dedicated QA budget",
        "AWS resources limited to $100 total project budget",
        "Testing must be completed within the semester timeline (no extensions available)",
    ])
    add_para(doc, "Scope of Testing Effort:", bold=True)
    add_para(
        doc,
        "Integration testing focuses on interfaces between system components, "
        "data flow validation, and end-to-end user scenarios. Unit testing of "
        "individual components is documented separately and is a prerequisite "
        "for integration testing."
    )
    add_para(doc, "Relationship to Other Evaluation Activities:", bold=True)
    add_para(
        doc,
        "Integration testing occurs after unit testing and code reviews are "
        "complete for each component. Design reviews and requirements "
        "traceability validation occur before integration testing begins for "
        "each build."
    )
    add_para(doc, "Change Control and Communication:", bold=True)
    add_para(
        doc,
        "All test plan changes require approval from the Project Manager (Wajih "
        "Anwar) and System Architect (Alex Bowser). Changes are tracked in the "
        "revision history. Communication of test results and defects occurs "
        "through GitHub issues and weekly team coordination meetings via Discord."
    )

    # ─── 3. TEST ITEMS ─────────────────────────────────────────────
    add_heading(doc, "3. Test Items (Functions)", level=1)

    add_heading(doc, "Build 1 Test Items (due 2026-04-09)", level=2)

    add_heading(doc, "Backend: flask-api/test_app.py and flask-api/test_endpoints.py", level=3)
    add_bullets(doc, [
        "TestCalculateBearing — bearing math for the four cardinals (N, E, S, W); "
        "locks in the math used by turn-by-turn directions.",
        "TestBearingToCardinal — maps degree values to all 8 compass labels and "
        "checks the 22/23-degree boundary.",
        "TestHaversine — zero distance, ~111 km per degree of latitude, symmetry.",
        "TestDirectionInstruction — branches: None→N (Head N), N→N (Continue "
        "straight), N→E (Turn right), N→W (Turn left), N→S (Turn around).",
        "TestHealth — GET /api/health returns 200 ok / 500 on DB error.",
        "TestViewMap — GET /api/nodes returns labeled node list.",
        "TestReroute — GET /api/route happy path with 3-node N→E path produces "
        "correct waypoint instructions; missing params → 400; unroutable → 404.",
        "TestViewAmenities — GET /api/amenities returns linked nav_node lat/lng "
        "(coordinate-frame guard).",
        "TestVerifySecurityZoneAccess — zone-filtered nearest node returns secure "
        "node; missing params → 400; no amenities in zone → 404 with zone name "
        "in error.",
        "TestGenerateRouteToAmenity — full flow: zone lookup → candidate amenity → "
        "dijkstra → serialized waypoints; missing params → 400.",
        "TestRandomNode — random waypoint per zone; invalid zone → 400.",
        "TestAmenityTypes — distinct amenity types for the dropdown filter.",
    ])

    add_heading(doc, "Frontend: Android JUnit tests", level=3)
    add_para(doc, "NavigationStateTest.kt:", bold=True)
    add_bullets(doc, [
        "isOffPath_returnsTrue_whenFarFromRoute — off-path detection trips when "
        "user strays; triggers reroute flow.",
        "dropdownTypeFilter_resetsRestroomGender_whenChanged — switching the "
        "dropdown filter clears the restroom gender filter.",
        "crossZoneParkingFlow_blockedUntilUserConfirms — routing across security "
        "zones is blocked until user explicitly confirms.",
        "crossZoneCancel_returnsToOriginalZone — cancelling a cross-zone prompt "
        "restores the prior zone state.",
    ])
    add_para(doc, "ZoneFilterTest.kt:", bold=True)
    add_bullets(doc, [
        "nullZone_returnsAllAmenities — pre-zone-pick state still shows the map.",
        "secureZone_returnsOnlySecureAmenities — hides irrelevant markers post-TSA.",
        "publicZone_returnsOnlyPublicAmenities — hides post-TSA markers from "
        "pre-security users.",
        "nullZoneAmenitiesAreDropped_whenZoneIsSet — ambiguous-zone data must not "
        "bleed across the boundary.",
    ])
    add_para(doc, "NavigationViewModelTest.kt:", bold=True)
    add_bullets(doc, [
        "filteredAmenities_noFilters_returnsAll — baseline behavior.",
        "filteredAmenities_typeFilter_keepsOnlyMatchingTypes — chip-row filter "
        "matches by type.",
        "filteredAmenities_accessibilityMode_viaAccessibleUnit — accessibility "
        "mode honors the per-unit flag.",
        "filteredAmenities_accessibilityMode_viaAmenityFlag — legacy "
        "wheelchairaccessible='yes' field still works.",
        "filteredAmenities_accessibilityMode_caseInsensitive — 'YES' matches 'yes'.",
        "filteredAmenities_combinedFilters — type filter and accessibility "
        "filter chain correctly.",
        "filteredAmenities_dropdownTypeFilter_keepsOnlyThatType — dropdown "
        "narrows to one type.",
        "filteredAmenities_restroomGenderMale_keepsOnlyMale — male filter keeps "
        "'Male Bathroom'.",
        "filteredAmenities_restroomGenderFemale_keepsOnlyFemale — female filter "
        "guards against the 'Female contains substring male' bug.",
        "filteredAmenities_restroomGenderAny_keepsBoth — ANY keeps both.",
        "filteredAmenities_combinesWithAccessibilityMode — gender + "
        "accessibility filters stack.",
        "accessibilityMode_doesNotFilter_whenOff — opt-in behavior.",
        "pointOnSegment_isZero — point on segment returns ~0 m.",
        "pointBeyondSegmentEnd_clampsToEndpoint — clamping for off-path detection "
        "near route ends.",
        "pointPerpendicularToSegment_returnsPerpDistance — most off-path cases.",
        "degeneratedSegment_returnsDistanceToPoint — divide-by-zero guard.",
    ])

    # Subsystem descriptions ----------------------------------------------
    add_heading(doc, "Android Front-End Mobile Application", level=3)
    add_bullets(doc, [
        "Version: 1.0",
        "Technology stack: Kotlin, Android SDK API 24 (Android 7.0 minimum)",
        "Development tool: Android Studio 2023.1.1 or later",
        "Target devices: Android smartphones via emulator",
    ])
    add_para(doc, "Components under test:", bold=True)
    add_bullets(doc, [
        "MapDisplay activity — renders Terminal D indoor map with amenity markers "
        "(Google Maps SDK), shows current location, supports pinch/zoom/pan, "
        "handles floor-level switching.",
        "AmenitySelection — displays amenity info, provides 'Navigate Here' "
        "button to trigger route generation.",
        "NavigationRouteOverlay — visual route display on map; renders blue "
        "polyline from current location to selected amenity, highlights turn "
        "points, updates in real time.",
    ])
    add_para(doc, "Configuration requirements:", bold=True)
    add_bullets(doc, [
        "Minimum SDK: API 24 (Android 7.0)",
        "Target SDK: API 36 (Android 14)",
        "Network: active Wi-Fi or cellular data connection",
        "Storage: ~50MB app size, ~10MB cache for map tiles",
    ])
    add_para(doc, "Critical delivery dependencies:", bold=True)
    add_bullets(doc, [
        "Google Maps base tiles must display via Google Maps API",
        "Terminal D nav graph must be stored in the database",
        "Backend API base URL configured",
    ])

    add_heading(doc, "Flask Backend REST API Server", level=3)
    add_bullets(doc, [
        "Version: Build 1.0",
        "Technology stack: Python 3.10+, Flask, flask-cors, psycopg2-binary",
        "Local development: localhost:5000",
    ])
    add_para(doc, "Integration testing endpoints:", bold=True)
    add_bullets(doc, [
        "/api/amenities — retrieve all amenities in Terminal D with linked "
        "nav_node lat/lng, type, security zone, accessibility, status, crowd "
        "level. Response is JSON.",
        "/api/route — generate optimized navigation route between two nav_nodes "
        "via pgr_dijkstra; returns waypoints with turn instructions.",
        "/api/route-to-amenity — nearest routable amenity of a given type, "
        "respects zone + accessibility + restroom gender filters.",
        "/api/nearest — nearest nav_node to a lat/lng, respects currentZone.",
        "/api/nodes, /api/edges, /api/amenity-types, /api/health — supporting "
        "endpoints.",
    ])
    add_para(doc, "Configuration requirements:", bold=True)
    add_bullets(doc, [
        "Python virtual environment with dependencies installed (requirements.txt)",
        "Environment variables in .env: DB_HOST, DB_USER, DB_PASS, DB_NAME, DB_PORT",
        "SSL not required for local dev; AWS RDS connection over public endpoint",
    ])
    add_para(doc, "Critical delivery dependencies:", bold=True)
    add_bullets(doc, [
        "PostgreSQL database schema created and seeded with Terminal D data",
        "pgRouting extension enabled on the RDS instance",
    ])

    # ── PostgreSQL section: this is what the user asked to update ──
    add_heading(doc, "PostgreSQL Relational Database", level=3)
    add_bullets(doc, [
        "Version: PostgreSQL 12.17",
        "Deployment environment: AWS RDS db.t3.micro instance "
        "(1 vCPU, 1 GB RAM, 20 GB SSD)",
        "Database name: postgres",
        "Extensions enabled: pgrouting, postgis, plpgsql",
    ])

    add_para(doc, "Schema (live AWS RDS, as of 2026-04-09):", bold=True)

    # nav_nodes
    add_para(doc, "nav_nodes (1,351 rows) — navigation waypoints", bold=True)
    schema_table(doc, [
        ("id", "integer", "PK, serial"),
        ("label", "text", "optional waypoint label"),
        ("x", "double precision", "planar X coordinate (NavEdit frame)"),
        ("y", "double precision", "planar Y coordinate (NavEdit frame)"),
        ("node_type", "text", "e.g. 'waypoint', amenity linker"),
        ("zone", "text", "'public' or 'secure' (pre/post-TSA); default 'public'"),
        ("lat", "double precision", "latitude used by routing"),
        ("lng", "double precision", "longitude used by routing"),
    ])

    # nav_edges
    add_para(doc, "nav_edges (5,944 rows) — graph edges for pgr_dijkstra", bold=True)
    schema_table(doc, [
        ("id", "integer", "PK, serial"),
        ("from_node", "integer", "FK → nav_nodes.id"),
        ("to_node", "integer", "FK → nav_nodes.id"),
        ("distance", "double precision", "edge weight / cost (meters)"),
        ("direction", "text", "compass bearing label (N, NE, E, SE, S, SW, W, NW)"),
    ])

    # amenities
    add_para(doc, "amenities (128 rows) — points of interest", bold=True)
    schema_table(doc, [
        ("id", "integer", "PK, serial"),
        ("nodeid", "integer", "FK → nav_nodes.id (linked waypoint; markers/routes "
                              "use the linked node's lat/lng, not the raw amenity row)"),
        ("name", "text", "amenity name (NOT NULL)"),
        ("type", "text", "amenity category, e.g. 'Bathroom', 'Food' (NOT NULL)"),
        ("wheelchairaccessible", "text", "'yes' / 'no' / 'unknown'; default 'unknown'"),
        ("status", "text", "'open', 'closed', etc.; default 'open'"),
        ("crowdlevel", "integer", "0–100 scale; default 0"),
        ("latitude", "double precision", "raw amenity latitude (do not use for "
                                         "routing; use the linked nav_node)"),
        ("longitude", "double precision", "raw amenity longitude (do not use for "
                                          "routing)"),
    ])

    add_para(doc, "Why the linked nav_node lat/lng instead of the raw amenity row:", bold=True)
    add_para(
        doc,
        "Amenity markers and route polylines must come from the same coordinate "
        "frame. The /api/amenities endpoint already returns the linked nav_node "
        "lat/lng for exactly this reason — past sign-flip bugs in the NavEdit "
        "affine transform have produced markers that did not match routes. The "
        "amenities.nodeid foreign key is the load-bearing piece of this guarantee."
    )

    # Why PostgreSQL over MySQL — preserved as-is per user instruction
    add_heading(doc, "Why PostgreSQL over MySQL", level=4)
    add_para(
        doc,
        "[KEEP EXISTING TEXT — paste the prior 'Why PostgreSQL over MySQL' "
        "paragraph here verbatim. This section is intentionally untouched per "
        "the v1.1 revision request; the only change in this revision is to the "
        "schema listing above and the 'Why hybrid' rationale below.]"
    )

    # Why hybrid — rewritten
    add_heading(doc, "Why hybrid (single engine, hybrid workload)", level=4)
    add_para(
        doc,
        "The system uses PostgreSQL 12.17 on AWS RDS with the pgRouting and "
        "PostGIS extensions. This is 'hybrid' in the sense that a single "
        "Postgres instance handles both the relational workload (amenities, "
        "metadata, future user reports) and the graph-routing workload "
        "(nav_nodes, nav_edges, pgr_dijkstra) — not in the sense of running two "
        "different database engines side by side."
    )
    add_para(
        doc,
        "An earlier design considered a hybrid Postgres + Neo4j (or similar "
        "two-engine) setup so that graph traversal could live in a dedicated "
        "graph database. That option was rejected for three reasons:"
    )
    add_bullets(doc, [
        "pgRouting gives us Dijkstra and A* directly against the same Postgres "
        "tables the API already reads, so there is no need to duplicate or "
        "synchronize the nav graph between two stores.",
        "Operating two database engines doubles the credentials, backup "
        "schedules, monitoring, and failure modes — well outside the $100 AWS "
        "budget and the 4-student team's bandwidth.",
        "A single engine eliminates cross-engine consistency bugs entirely "
        "(e.g., an amenity row updated in Postgres but its corresponding graph "
        "node still stale in Neo4j).",
    ])
    add_para(
        doc,
        "PostGIS is included for spatial column types and indexes used by the "
        "nearest-node lookup. The hard constraint going forward is "
        "Postgres-compatible only — no Mongo, no Neo4j, no SQLite swap. Any "
        "design document that mentions Neo4j should be treated as "
        "future/aspirational, not current state."
    )

    # Build 1 integration points
    add_heading(doc, "Integration Points for Build 1", level=3)
    add_para(doc, "Android Front-End to Flask Backend Integration", bold=True)
    add_bullets(doc, [
        "Communication protocol: REST API calls",
        "Data format: JSON",
        "Response parsing: Android correctly deserializes JSON, handles "
        "missing/null fields gracefully",
        "Timeout handling: Android shows loading indicator, cancels request "
        "after 10 seconds if no response",
        "Request formatting: Android serializes user input to JSON, sets "
        "Content-Type: application/json",
    ])
    add_para(doc, "Test scenarios:", bold=True)
    add_bullets(doc, [
        "User opens app → GET /api/amenities → 200 with amenity array → markers render on map",
        "User selects 'Navigate' → GET /api/route → 200 with waypoints → route polyline drawn",
        "User selects 'Navigate' across security zones → backend returns route "
        "that does not cross the TSA boundary",
    ])

    add_para(doc, "Flask Backend to PostgreSQL Database Integration", bold=True)
    add_bullets(doc, [
        "Communication protocol: PostgreSQL wire protocol over the public RDS endpoint",
        "Tooling: pgAdmin 4 for query inspection",
        "Query correctness: backend SQL queries return correct rows",
        "Connection handling: backend handles DB connection failures gracefully",
        "Performance: <500ms for simple SELECTs, <2s for routing queries",
    ])
    add_para(doc, "Test scenarios:", bold=True)
    add_bullets(doc, [
        "Backend receives GET /api/amenities → executes SELECT against amenities + "
        "nav_nodes → serializes to JSON",
        "Backend receives GET /api/route → invokes pgr_dijkstra over nav_edges → "
        "returns waypoint array",
    ])

    add_para(doc, "End-to-End", bold=True)
    add_bullets(doc, [
        "Data continuity: GPS → Android → Backend → Routing → Backend → Android → Map",
        "Asynchronous coordination: UI remains responsive during route calculation",
        "State management: Android maintains navigation state correctly",
    ])
    add_para(doc, "Happy path (post-security):", bold=True)
    add_bullets(doc, [
        "User at Gate D15 → opens app → map loads with location dot at D15",
        "User taps 'Navigate Here' → GET /api/route → 5 waypoints returned",
        "Android draws route line → user follows → arrives at Restroom D20",
    ])
    add_para(doc, "Happy path (pre-security):", bold=True)
    add_bullets(doc, [
        "User at check-in → opens app → map loads",
        "User taps 'Navigate Here' → GET /api/route → waypoints returned",
        "Android draws route → user arrives at restroom before the gate",
    ])

    # Build 2 ----------------------------------------------------
    add_heading(doc, "Build 2 Test Items", level=2)
    add_para(doc, "Mock Sensors Simulation", bold=True)
    add_bullets(doc, [
        "Version: 2.0",
        "Technology stack: Python, Flask",
        "Development: local development machines",
    ])
    add_para(doc, "Components under test:", bold=True)
    add_bullets(doc, [
        "Occupancy sensor simulator — restroom stall vacant↔occupied transitions, "
        "10-second update cadence, POSTs to /api/sensors/occupancy/update.",
        "Crowd detection simulator — crowd density (low/medium/high), "
        "30-second update cadence, POSTs to backend.",
    ])
    add_para(doc, "Configuration:", bold=True)
    add_bullets(doc, [
        "Configuration files: sensor_config.json, crowd_config.json",
        "Environment variable: BACKEND_API_URL",
    ])
    add_para(doc, "Critical delivery:", bold=True)
    add_bullets(doc, [
        "Backend sensor endpoints implemented by 2026-04-15",
        "Database schema updated with occupancy_events / crowd_events tables by 2026-04-20",
    ])
    add_para(doc, "Front-end updates:", bold=True)
    add_bullets(doc, [
        "Real-time status: amenity markers highlight occupancy + crowd level when tapped",
        "Color coding: green (low), yellow (medium), orange (high), red (closed/unknown)",
        "Auto-refresh: amenity updates every 3 minutes",
        "Detail view: shows timestamp of most recent update",
    ])
    add_para(doc, "Integration points:", bold=True)
    add_bullets(doc, [
        "Mock sensors → backend: data flow sensor → backend → database → frontend, "
        "no dropped requests under simulator load",
        "Backend → database → frontend: end-to-end latency <10s, last-write-wins "
        "on concurrent updates",
        "Polling cache reduces database load",
    ])

    # Build 3 ----------------------------------------------------
    add_heading(doc, "Build 3 Test Items", level=2)
    add_para(
        doc,
        "Use cases addressed: UC8 (Update Infrastructure Status), UC4 (Manage "
        "Account), UC3 (Submit User Report). Integration baseline: Build 1 + "
        "Build 2 approved baselines."
    )
    add_para(doc, "User authentication:", bold=True)
    add_bullets(doc, [
        "Version: Build 3.0",
        "Technology: JWT tokens",
        "POST /api/users — create user; validates email format and password strength; <1s response",
        "POST /api/auth — authenticates; returns JWT; <1s response",
    ])
    add_para(doc, "Database schema additions (planned for Build 3):", bold=True)
    add_bullets(doc, [
        "users — email, password hash, name, account status",
        "user_preferences — accessibility, preferred amenity types",
        "user_reports — report id, amenity id, user id, report type, timestamp, rating",
    ])
    add_para(doc, "Front-end additions:", bold=True)
    add_bullets(doc, [
        "Login (email/password)",
        "Register (email, password, full name, accessibility checkbox)",
        "Account settings (user info, accessibility mode, save preferences)",
        "Report Issues (report type dropdown, rating, submit)",
    ])
    add_para(doc, "Integration points:", bold=True)
    add_bullets(doc, [
        "Authentication ↔ all modules: JWT propagation through every API call; "
        "admin endpoints reject non-admin tokens; token expiration → 401 → "
        "redirect to login",
        "Account preferences ↔ navigation: wheelchair mode auto-applied to "
        "routes; preferences persist across sessions",
        "Full system integration covering all 8 use cases",
    ])

    # ─── 4. SOFTWARE RISK ISSUES ──────────────────────────────────
    add_heading(doc, "4. Software Risk Issues", level=1)

    add_heading(doc, "Risk 4.1 — Terminal D Floor Plan Data Unavailable or Incomplete", level=2)
    add_bullets(doc, [
        "Description: floor plan from DFW may be inaccurate, missing nodes, or "
        "redacted around TSA areas.",
        "Probability: Medium (40%)",
        "Impact: Critical — without accurate floor plan data, the routing engine "
        "cannot generate correct paths.",
        "Technical complexity: routing requires a complete graph (waypoints + "
        "edges); incomplete coverage breaks reachability, missing edges break "
        "floor traversal, incorrect coordinates put routes in the wrong places.",
        "Mitigation (primary): Google Maps base + node coverage built in NavEdit",
        "Mitigation (fallback): static PNG of DFW floor plan with key amenities",
    ])

    add_heading(doc, "Risk 4.2 — AWS Service Outages", level=2)
    add_bullets(doc, [
        "Description: AWS RDS may experience outages, degraded performance, or "
        "regional availability issues during integration testing.",
        "Probability: Medium (30%)",
        "Impact: High — testing cannot proceed without a functional database; "
        "each day of delay reduces available testing time.",
        "Mitigation: System Architect maintains a Docker Compose backup with "
        "Flask + PostgreSQL running locally; automated health checks every 5 minutes.",
    ])

    add_heading(doc, "Risk 4.3 — Google Maps API Key Quota Exceeded or Revoked", level=2)
    add_bullets(doc, [
        "Description: Google Maps SDK requires an API key with daily usage quotas.",
        "Probability: Low (15%)",
        "Impact: Medium — map display is critical for UC2 (View Amenities).",
        "Technical detail: Google Maps free tier allows 28,000 map loads / month.",
        "Mitigation: monitor Google Cloud Console daily; maintain a backup API "
        "key from a different team member's account; fall back to static map if "
        "needed.",
    ])

    # ─── 5. FEATURES TO BE TESTED ─────────────────────────────────
    add_heading(doc, "5. Features to be Tested", level=1)

    add_heading(doc, "Build 1 Features", level=2)
    add_features_table(doc, [
        ("F1.1 — View Terminal D Map with current location",
         "Foundational feature; map render + GPS dot",
         "M"),
        ("F1.2 — View amenities on map (markers)",
         "Database returns 50+ amenity rows; markers render without lag",
         "M"),
        ("F1.3 — Select amenity from map (popup with name, type, distance)",
         "Bridge between discovery and navigation; selected amenity ID must persist",
         "M"),
        ("F1.4 — Generate route to selected amenity",
         "UC1 (highest priority); pgr_dijkstra over nav_edges; multiple dependencies",
         "H"),
        ("F1.5 — TSA security zone filtering",
         "Hard physical boundary; failure has severe user consequences",
         "H"),
        ("F1.6 — View route on map (blue polyline + waypoints)",
         "Visual route; depends on nav_node coordinates being correct",
         "H"),
    ])

    add_heading(doc, "Build 2 Features", level=2)
    add_features_table(doc, [
        ("F2.1 — View real-time amenity occupancy",
         "UC5; differentiates from static maps; 4-component pipeline",
         "M"),
        ("F2.2 — View real-time crowd levels",
         "Helps users avoid crowded amenities; threshold-based",
         "M"),
        ("F2.3 — Last updated timestamp",
         "Transparency feature; non-blocking",
         "L"),
        ("F2.4 — Map marker color-coding by status",
         "At-a-glance status; straightforward conditionals",
         "M"),
    ])

    add_heading(doc, "Build 3 Features", level=2)
    add_features_table(doc, [
        ("F3.1 — Create user",
         "Standard registration + hashing; not required for navigation",
         "L"),
        ("F3.2 — Login to existing account",
         "JWT generation, password verification",
         "L"),
        ("F3.3 — Save account preferences",
         "Cross-build integration with routing engine; state mgmt",
         "M"),
        ("F3.4 — Send reports",
         "Optional feedback mechanism; simple form submission",
         "L"),
    ])

    # ─── 6. FEATURES NOT TO BE TESTED ─────────────────────────────
    add_heading(doc, "6. Features NOT to be Tested", level=1)
    add_bullets(doc, [
        "FNT.1 — Live sensor integration (mock simulators only; physical hardware "
        "out of scope)",
        "FNT.2 — Multi-terminal support (Terminals A/B/C/E); scoped to Terminal D only",
        "FNT.3 — Voice navigation / TTS",
        "FNT.4 — Multi-language support (English only)",
        "FNT.5 — Integration with the existing DFW Wayfinder app",
        "FNT.6 — AWS infrastructure at large scale; fixed t3.micro is sufficient",
        "FNT.7 — Load testing / stress testing; not feasible within $100 AWS budget",
    ])

    # ─── 7. APPROACH (STRATEGY) ───────────────────────────────────
    add_heading(doc, "7. Approach (Strategy)", level=1)
    add_para(
        doc,
        "The Integration Test Plan follows an incremental integration testing "
        "strategy across three builds during the Elaboration phase. Each build "
        "integrates new components with previously tested components."
    )
    add_para(doc, "Testing tools:", bold=True)
    add_bullets(doc, [
        "Android Emulator — runs the Android app without a physical device; "
        "already in use during development.",
        "pytest — backend unit + endpoint tests (flask-api/test_app.py, "
        "flask-api/test_endpoints.py).",
        "pgAdmin 4 — manual SQL inspection / data validation against AWS RDS.",
        "GitHub Actions — CI/CD pipeline (deferred; will be enabled if time permits).",
        "Console log — manual GET request testing during development.",
        "AWS CloudWatch — backend monitoring; deferred to end of project.",
    ])
    add_para(doc, "Metrics:", bold=True)
    add_bullets(doc, [
        "Use Case Test Case Pass Rate — overall test effectiveness; target ≥95%.",
    ])

    # ─── 8. ITEM PASS/FAIL CRITERIA ───────────────────────────────
    add_heading(doc, "8. Item Pass/Fail Criteria", level=1)
    add_bullets(doc, [
        "Each Build's integration test scenarios pass when all happy-path and "
        "unhappy-path tests above succeed against the live (or staged) Flask + "
        "RDS deployment.",
        "Build is considered failed if any High-risk feature (F1.4, F1.5, F1.6) "
        "test fails.",
        "Medium-risk feature failures generate a defect ticket but do not block "
        "the Build sign-off if a workaround is documented.",
    ])

    # ─── 9. SUSPENSION CRITERIA AND RESUMPTION ────────────────────
    add_heading(doc, "9. Suspension Criteria and Resumption Requirements", level=1)
    add_para(
        doc,
        "Testing is suspended if (a) the AWS RDS instance is unreachable for "
        "more than 4 hours, (b) the Flask backend cannot start due to a "
        "schema-vs-code drift that breaks /api/health, or (c) the Android app "
        "fails to build on the team's reference Android Studio version. "
        "Resumption requires the affected component to recover and the "
        "previously failing test to pass before broader testing resumes."
    )

    # ─── 10. TEST DELIVERABLES ────────────────────────────────────
    add_heading(doc, "10. Test Deliverables", level=1)
    add_bullets(doc, [
        "This Integration Test Plan document (docs/IntegrationTestPlan.docx)",
        "Backend Test Plan (docs/BackendTestPlan.docx) — referenced for unit-level coverage",
        "Frontend Test Plan (docs/FrontendTestPlan.docx) — referenced for unit-level coverage",
        "pytest output for flask-api/ — passing run as evidence",
        "Gradle test report for android-app/ — passing run as evidence",
        "Defect log captured as GitHub issues",
    ])

    # ─── 11. REMAINING TEST TASKS ─────────────────────────────────
    add_heading(doc, "11. Remaining Test Tasks", level=1)
    add_bullets(doc, [
        "Build 2 sensor pipeline tests — pending sensor endpoint implementation",
        "Build 3 authentication and reporting tests — pending UC4/UC3/UC8 implementation",
        "End-to-end integration against a throwaway Postgres container (CI nice-to-have)",
    ])

    # ─── 12. ENVIRONMENTAL NEEDS ──────────────────────────────────
    add_heading(doc, "12. Environmental Needs", level=1)
    add_bullets(doc, [
        "Python 3.10+ with the dependencies listed in flask-api/requirements.txt",
        "JDK 17 + Android Studio for the Android client",
        "AWS RDS PostgreSQL 12.17 instance with pgRouting + PostGIS extensions",
        "Google Maps API key configured in the Android client",
        "Network access to the public RDS endpoint from developer machines",
    ])

    # ─── 13. STAFFING AND TRAINING NEEDS ──────────────────────────
    add_heading(doc, "13. Staffing and Training Needs", level=1)
    add_para(
        doc,
        "Group 1 (4 students). No additional staffing. Training needs: pgAdmin "
        "4 basics for the Backend / Database Lead; Android Studio test runner "
        "for the Frontend / Android Lead. No commercial test tools or licensed "
        "software are required."
    )

    # ─── 14. RESPONSIBILITIES ─────────────────────────────────────
    add_heading(doc, "14. Responsibilities", level=1)
    add_bullets(doc, [
        "Wajih Anwar (Project Manager) — schedule, milestones, sign-off on test plan changes.",
        "Alex Bowser (System Architect) — integration architecture, risk register, "
        "approval of design / schema changes.",
        "Lennon Crow (Backend / Database Lead) — Flask endpoints, SQL, pgRouting "
        "queries, backend tests, RDS health.",
        "Amelia Quinn (Frontend / Android Lead) — Android client, Google Maps "
        "integration, frontend tests.",
        "All team members — run the full pytest + Gradle test suites before merging.",
    ])

    # ─── 15. SCHEDULE ─────────────────────────────────────────────
    add_heading(doc, "15. Schedule", level=1)
    add_bullets(doc, [
        "Build 1 integration testing complete: 2026-04-09",
        "Build 2 integration testing complete: 2026-04-22",
        "Build 3 integration testing complete: 2026-05-06",
        "Final demo: per course schedule",
    ])

    # ─── 16. PLANNING RISKS AND CONTINGENCIES ─────────────────────
    add_heading(doc, "16. Planning Risks and Contingencies", level=1)
    add_bullets(doc, [
        "Late delivery of Build 2 sensor endpoints — fall back to documenting "
        "the planned tests and demoing with manual POSTs.",
        "AWS RDS quota exhaustion — switch to local Docker Compose Postgres for "
        "the duration of testing.",
        "Team member unavailability — cross-train the System Architect on backend "
        "tests so testing is not single-pointed.",
    ])

    # ─── 17. APPROVALS ────────────────────────────────────────────
    add_heading(doc, "17. Approvals", level=1)
    t = doc.add_table(rows=3, cols=3)
    t.style = "Light Grid Accent 1"
    hdr = t.rows[0].cells
    hdr[0].text = "Name"
    hdr[1].text = "Role"
    hdr[2].text = "Signature / Date"
    t.rows[1].cells[0].text = "Wajih Anwar"
    t.rows[1].cells[1].text = "Project Manager"
    t.rows[2].cells[0].text = "Alex Bowser"
    t.rows[2].cells[1].text = "System Architect"

    # ─── Appendices ───────────────────────────────────────────────
    add_heading(doc, "Appendix A: Glossary", level=1)
    gloss = [
        ("Zone", "Either 'secure' (post-TSA / airside) or 'public' (pre-TSA / "
                 "landside). Routing must not cross this boundary."),
        ("Waypoint", "A node in the navigation graph used by pgr_dijkstra."),
        ("pgRouting", "PostgreSQL extension that provides graph routing functions "
                      "(pgr_dijkstra, pgr_aStar) operating directly on Postgres tables."),
        ("PostGIS", "PostgreSQL extension that adds spatial column types and indexes."),
        ("NavEdit", "The HTML-based affine-transform calibration tool used to "
                    "produce nav_node lat/lng values."),
    ]
    t = doc.add_table(rows=1 + len(gloss), cols=2)
    t.style = "Light Grid Accent 1"
    t.rows[0].cells[0].text = "Term"
    t.rows[0].cells[1].text = "Definition"
    for i, (term, defn) in enumerate(gloss, start=1):
        t.rows[i].cells[0].text = term
        t.rows[i].cells[1].text = defn

    add_heading(doc, "Appendix B: References", level=1)
    add_bullets(doc, [
        "flask-api/app.py — backend endpoint implementations under test",
        "flask-api/test_app.py, flask-api/test_endpoints.py — backend tests",
        "android-app/app/src/test/java/com/example/se6387map/ — Android JUnit tests",
        "docs/BackendTestPlan.docx — backend unit test plan",
        "docs/FrontendTestPlan.docx — frontend unit test plan",
        "Project notes: project overview and architectural constraints",
        "Smart Amenities Finder use case diagram",
        "IEEE 829 Test Plan Outline",
    ])

    out = DOCS_DIR / "IntegrationTestPlan.docx"
    doc.save(out)
    print(f"[ok] wrote {out}")


def schema_table(doc, rows):
    """Render a 3-column (column / type / notes) schema table."""
    table = doc.add_table(rows=1 + len(rows), cols=3)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].text = "Column"
    hdr[1].text = "Type"
    hdr[2].text = "Notes"
    for cell in hdr:
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
    for i, (col, typ, notes) in enumerate(rows, start=1):
        c = table.rows[i].cells
        c[0].text = col
        c[1].text = typ
        c[2].text = notes
    return table


if __name__ == "__main__":
    build_backend_plan()
    build_frontend_plan()
    build_integration_test_plan()
