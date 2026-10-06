# ArcGIS Alerts

A Home Assistant integration that turns any ArcGIS polygon feature layer into a binary sensor: **on**
while at least one feature of the layer covers a location you choose, with the matching features'
fields as attributes. Set it up from the UI; no `configuration.yaml`.

The first preset is the Sewerage and Water Board of New Orleans (SWBNO) boil water advisory map,
so a boil water advisory can say not only that one is in effect but which one, since when, and
what it covers.

## Install

1. In HACS, open the menu, choose **Custom repositories**, and add
   `https://github.com/vilemaxim/ha-arcgis-alerts` with type **Integration**.
2. Download **ArcGIS Alerts** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → ArcGIS Alerts.**

Each entry is one layer and one location. Add the integration again for another.

## The sensor

One binary sensor per entry, on when a feature covers the location. Attributes:

| Attribute | What it holds |
| --- | --- |
| `count` | How many features cover the location |
| `title` | The title field of the first matching feature |
| `features` | Up to 10 matching features, each a dict of fields; dates as ISO 8601 UTC |
| `layer_url` | The layer queried |

If the layer cannot be reached, or answers with an ArcGIS error, the sensor becomes
**unavailable**, never a false **off**.

## Presets

| Preset | Layer | Filter | Device class |
| --- | --- | --- | --- |
| SWBNO boil water advisory (New Orleans) | `SWB_Advisory_Area_VIEW/FeatureServer/0` on ArcGIS Online | `Adv_Status IN ('active','testing')` | `problem` |

The SWBNO preset exposes `Advisory_Title`, `Advisory_Details`, `Adv_Type` (`BWA` precautionary
advisory, `BWO` order), `Adv_Status`, and `Public_Begin_DT`. SWBNO uses the `testing` status for
drills, so the sensor turns on for those too.

Adding a preset is a data-only change: one entry in `PRESETS` in
`custom_components/arcgis_alerts/const.py` and its label under `selector.preset.options` in
`strings.json` and `translations/en.json`. Pull requests welcome.

## Custom layers

Choose **Custom layer** and give:

- **Layer URL** — a FeatureServer or MapServer layer of polygons, ending in the layer number, such
  as `https://services1.arcgis.com/<org>/arcgis/rest/services/<service>/FeatureServer/0`.
- **Where clause** — an SQL filter the layer applies, such as `Status = 'active'`. `1=1` takes
  every feature.
- **Title field** — optional; the field that fills the `title` attribute.
- **Device class** — optional; how Home Assistant shows the sensor.

The integration reads `<layer URL>?f=json` and refuses a layer that is not polygons or does not
allow queries.

### Finding a layer URL

- **From a web map or dashboard.** Open the browser's developer tools, Network tab, and filter for
  `FeatureServer` or `MapServer`. The URL of a `query` request, up to and including the number
  before `/query`, is the layer URL.
- **From ArcGIS Hub or an open data portal.** On the dataset's page, look for **I want to use
  this → View API resources** or **APIs → GeoService**; that is the layer URL.
- **From the service directory.** Open `.../arcgis/rest/services`, follow the service, and pick
  the layer. The layer page lists its **Geometry Type** (must be `esriGeometryPolygon`), its
  fields, and **Supported Operations** (must include `Query`).

## Query modes

Set per entry under **Configure**.

| Mode | What is sent to the layer's host | Where the location is checked |
| --- | --- | --- |
| **Local** (default) | The where clause only | In Home Assistant: the matching features' polygons are downloaded and tested against your location |
| **Server** | The where clause **and your location** | On the layer's host, with `esriSpatialRelIntersects` |

Local mode keeps your location private, and suits layers with a modest number of matching
features. Use server mode for layers too large to download on every poll; it shares your location
with whoever runs the layer.

The options also set the poll interval (default 5 minutes, minimum 1), the where clause, and the
location.

## Example automation

```yaml
automation:
  - alias: Boil water advisory notification
    triggers:
      - trigger: state
        entity_id: binary_sensor.swbno_boil_water_advisory
        to: "on"
    actions:
      - action: notify.notify
        data:
          title: "Boil water: {{ state_attr(trigger.entity_id, 'title') }}"
          message: >
            {% set f = state_attr(trigger.entity_id, 'features')[0] %}
            {{ f.Advisory_Details }} ({{ f.Adv_Type }}), in effect since
            {{ as_local(as_datetime(f.Public_Begin_DT)).strftime('%b %-d %-I:%M %p') }}.
```

## Development

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

Tests run against recorded responses in `tests/fixtures/`; they make no network calls.

## License

MIT
