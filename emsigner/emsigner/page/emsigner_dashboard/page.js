frappe.pages["live-dashboard---fms"].on_page_load = function (wrapper) {
  new MyPage(wrapper);
};

// PAGE CONTENT
var MyPage = Class.extend({
  init: function (wrapper) {
    this.page = frappe.ui.make_app_page({
      parent: wrapper,
      title: "Live Dashboard",
      single_column: true,
    });
    this.make();
  },

  make: function () {
    let me = this;
    frappe.call({
      method: "erpnext_vehicle_trip_tracking.api.trip.get_today_run_summary",
      callback: function (r) {
        console.log(r);
        // Clear existing table rows
        $("#vehicle-table tbody").empty();
        // Iterate over the response message and append rows to the table
        r.message.forEach((trip, index) => {
          let newRow = `
                        <tr data-route="${trip.trip_route}" trip-id="${
            trip.trip_id
          }" data-schedule="${trip.schedule_id}" data-vehicle-number="${
            trip.vehicle
          }" data-lat="${trip.lat}" data-lng="${trip.lng}" data-timestamp="${
            trip.trip_date
          }" data-tracking-url="${trip.tracking_url}">
                            <td>${index + 1}</td>
                            <td>${trip.trip_route}</td>
                            <td>${trip.schedule_id}</td>
                            <td>${trip.vehicle}</td>
                        </tr>
                    `;
          $("#vehicle-table tbody").append(newRow);
        });

        // Add click event listener to table rows
        $("#vehicle-table tbody tr").on("click", function (e) {
          const tripId = $(e.currentTarget).attr("trip-id");
          if (tripId) {
            frappe.call({
              method:
                "erpnext_vehicle_trip_tracking.api.trip.get_vehicle_run_details",
              args: {
                trip_id: tripId,
              },
              callback: function (r) {
                if (r.message) {
                  showVehicleDetails(
                    r.message.attender || "-",
                    r.message.delay_in_minutes || "-",
                    r.message.driver_1 || "-",
                    r.message.driver_2 || "-",
                    r.message.expected_arrival_time || "-",
                    r.message.operation_type || "-",
                    r.message.operations_incharge || "-",
                    r.message.schedule_id,
                    r.message.scheduled_time,
                    r.message.select_vehicle_seating_type || "-",
                    r.message.trip_date,
                    r.message.trip_route,
                    r.message.trip_status,
                    r.message.vehicle_number,
                    r.message.tracking_url || "-"
                  );
                }
              },
            });
          }
        });

        // Trigger click event on the first row to display its details by default
        $("#vehicle-table tbody tr:first").trigger("click");
      },
    }); 

    // Body content with updated table structure
    let body = `
            <div style="display: flex; gap: 1rem;" id="content-container;">
                <div id="table-container" style="flex-grow: 1;">
                    <table id="vehicle-table" class="table table-bordered" style="background-color: #f8f9fa; padding: 1rem; border: 1px solid #dee2e6; border-radius: 0.25rem; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Route</th>
                                <th>Schedule ID</th>
                                <th>Vehicle Number</th>
                            </tr>
                        </thead>
                        <tbody>
                            <!-- Rows will be appended here dynamically -->
                        </tbody>
                    </table>
                </div>
                <div id="details-container" class="d-none" style="width: 60%; background-color: #f8f9fa; padding: 1rem; border: 1px solid #dee2e6; border-radius: 0.25rem; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1); overflow-y: auto; height: 700px; margin-top: 20px;">
                    <!-- Vehicle details and map will be shown here -->
                    <div id="map" style="height: 300px;"></div>
                    <div id="tracking-map" style="height: 400px;"></div>
                </div>
            </div>
        `;

    $(frappe.render_template(body, this)).appendTo(this.page.main);

    // Initialize Leaflet Map with default coordinates
    let map = L.map("map").setView([11.127123, 78.656891], 12);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    // Function to show vehicle details
    function showVehicleDetails(
      attender,
      delay_in_minutes,
      driver_1,
      driver_2,
      expected_arrival_time,
      operation_type,
      operations_incharge,
      schedule_id,
      scheduled_time,
      select_vehicle_seating_type,
      trip_date,
      trip_route,
      trip_status,
      vehicle_number,
      tracking_url
    ) {
      // Populate details container with vehicle data
      $("#details-container").html(`
                <h2 style="font-size: 1.5rem; margin-bottom: 0.5rem;">Vehicle Details</h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Vehicle Number</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${vehicle_number}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Trip Date</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${trip_date}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Trip Route</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${trip_route}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Operation Type</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${operation_type}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Operations Incharge</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${operations_incharge}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Attender</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${attender}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Driver 1</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${driver_1}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Driver 2</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${driver_2}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Seating Type</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${select_vehicle_seating_type}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Last Point Scheduled Time</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${scheduled_time}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Expected Arrival Time</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${expected_arrival_time}</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Delay in Minutes</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;">${delay_in_minutes} minutes</td>
                    </tr>
                    <tr>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><strong>Tracking URL</strong></td>
                        <td style="font-size: 1rem; color: #333; padding: 0.5rem; border: 1px solid #dee2e6;"><a href="${tracking_url}" target="_blank">${tracking_url}</a></td>
                    </tr>
                </table>
                <div id="tracking-map" style="height: 400px; margin-top: 1rem;"></div>
            `);

      // Adjust layout
      $("#table-container").css("flex-basis", "40%");
      $("#details-container").removeClass("d-none").css("display", "block");

      // Load map from tracking URL in iframe
      loadTrackingMap(tracking_url);
    }

    // Function to load map from tracking URL in iframe
    function loadTrackingMap(trackingUrl) {
      $("#tracking-map").html("");
      if (trackingUrl) {
        let iframe = $("<iframe></iframe>");
        iframe.attr("src", trackingUrl);
        iframe.attr("width", "100%");
        iframe.attr("height", "100%");
        iframe.attr("frameborder", "0");
        iframe.appendTo($("#tracking-map"));
      }
    }

    // Load Leaflet CSS and JS dynamically
    let leafletCss = document.createElement("link");
    leafletCss.rel = "stylesheet";
    leafletCss.href = "https://unpkg.com/leaflet@1.7.1/dist/leaflet.css";
    document.head.appendChild(leafletCss);

    let leafletJs = document.createElement("script");
    leafletJs.src = "https://unpkg.com/leaflet@1.7.1/dist/leaflet.js";
    leafletJs.async = true;
    leafletJs.defer = true;
    document.head.appendChild(leafletJs);
  },
});