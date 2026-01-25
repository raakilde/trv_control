console.info(
  '%c TRV-CONTROL-CARD %c v1.0.3 ',
  'color: orange; font-weight: bold; background: black',
  'color: white; font-weight: bold; background: dimgray'
);

console.log('TRV Control Card: Script loading...');

class TRVControlCard extends HTMLElement {
  constructor() {
    super();
    this._isDragging = false;
    this._dragTarget = null;
  }

  set hass(hass) {
    this._hass = hass;

    if (!this.content) {
      this.innerHTML = `
        <ha-card>
          <div class="card-content"></div>
        </ha-card>
      `;
      this.content = this.querySelector('.card-content');
    }

    const entityId = this.config.entity;
    const stateObj = hass.states[entityId];

    if (!stateObj) {
      this.content.innerHTML = `
        <div class="not-found">Entity ${entityId} not found</div>
      `;
      return;
    }

    const attrs = stateObj.attributes;
    const currentTemp = attrs.current_temperature || 0;
    const targetTemp = attrs.temperature || 20;
    const minTemp = attrs.min_temp || 5;
    const maxTemp = attrs.max_temp || 30;
    const step = attrs.target_temp_step || 0.5;
    const heatingStatus = attrs.heating_status || 'unknown';
    const windowOpen = attrs.window_open || false;
    const trvCount = attrs.trv_count || 0;

    // Performance monitoring attributes
    const performanceScore = attrs.performance_efficiency_score;
    const tempAccuracy = attrs.performance_temperature_accuracy;
    const controlStability = attrs.performance_control_stability;
    const runtimeHours = attrs.performance_runtime_hours;
    const totalActions = attrs.performance_total_actions;
    const valveAdjustments = attrs.performance_valve_adjustments;
    const actionsPerHour = attrs.performance_actions_per_hour;
    const maxTempDev = attrs.performance_max_temp_deviation;
    const avgTempDev = attrs.performance_avg_temp_deviation;
    const nightSavingUses = attrs.performance_night_saving_uses;
    const windowEvents = attrs.performance_window_events;
    const nightSavingActive = attrs.night_saving_active || false;
    const adjustedTargetTemp = attrs.adjusted_target_temp;

    // Get all TRV data with validation
    const trvs = [];
    for (let key in attrs) {
      if (key.endsWith('_entity') && !key.startsWith('temp_sensor') && !key.startsWith('window_sensor')) {
        const trvPrefix = key.replace('_entity', '');
        const trvEntityId = attrs[key];
        const trvEntityState = hass.states[trvEntityId];
        
        // Get actual TRV state for validation
        const actualSetpoint = trvEntityState ? trvEntityState.attributes.temperature : null;
        const actualValvePosition = trvEntityState ? (
          trvEntityState.attributes.valve_position || 
          trvEntityState.attributes.position || 
          trvEntityState.attributes.valve_opening
        ) : null;
        
        // Get expected values from TRV control
        const expectedSetpoint = nightSavingActive && adjustedTargetTemp ? adjustedTargetTemp : targetTemp;
        const expectedValvePosition = attrs[`${trvPrefix}_valve_position`];
        
        // Validate setpoint (allow 0.5°C tolerance)
        const setpointValid = actualSetpoint !== null && 
          Math.abs(actualSetpoint - expectedSetpoint) <= 0.5;
        
        // Validate valve position (allow 5% tolerance)
        const valvePositionValid = actualValvePosition !== null && expectedValvePosition !== null &&
          Math.abs(actualValvePosition - expectedValvePosition) <= 5;
        
        trvs.push({
          name: trvPrefix.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
          entity: trvEntityId,
          returnTemp: attrs[`${trvPrefix}_return_temp`],
          returnSensor: attrs[`${trvPrefix}_return_temp_sensor`],
          valvePosition: expectedValvePosition,
          actualValvePosition: actualValvePosition,
          valvePositionValid: valvePositionValid,
          valveActive: attrs[`${trvPrefix}_valve_control_active`],
          closeThreshold: attrs[`${trvPrefix}_close_threshold`],
          openThreshold: attrs[`${trvPrefix}_open_threshold`],
          maxPosition: attrs[`${trvPrefix}_max_position`], 
          anticipatoryOffset: attrs[`${trvPrefix}_anticipatory_offset`], 
          status: attrs[`${trvPrefix}_status`],
          statusReason: attrs[`${trvPrefix}_status_reason`],
          expectedSetpoint: expectedSetpoint,
          actualSetpoint: actualSetpoint,
          setpointValid: setpointValid
        });
      }
    }

    const statusIcon = {
      'heating': 'mdi:fire',
      'target_reached': 'mdi:check-circle',
      'off': 'mdi:power-off',
      'window_open': 'mdi:window-open'
    }[heatingStatus] || 'mdi:help-circle';

    const statusColor = {
      'heating': '#ff9800',
      'target_reached': '#4caf50',
      'off': '#9e9e9e',
      'window_open': '#2196f3'
    }[heatingStatus] || '#9e9e9e';

    // Calculate gauge parameters (0-270 degree range, starting from -135deg)
    const tempRange = maxTemp - minTemp;
    const currentPercent = (currentTemp - minTemp) / tempRange;
    const targetPercent = (targetTemp - minTemp) / tempRange;

    // SVG arc calculation helpers
    const polarToCartesian = (centerX, centerY, radius, angleInDegrees) => {
      const angleInRadians = (angleInDegrees - 90) * Math.PI / 180.0;
      return {
        x: centerX + (radius * Math.cos(angleInRadians)),
        y: centerY + (radius * Math.sin(angleInRadians))
      };
    };

    const describeArc = (x, y, radius, startAngle, endAngle) => {
      const start = polarToCartesian(x, y, radius, endAngle);
      const end = polarToCartesian(x, y, radius, startAngle);
      const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
      return [
        "M", start.x, start.y,
        "A", radius, radius, 0, largeArcFlag, 0, end.x, end.y
      ].join(" ");
    };

    // Calculate arcs for the circular slider (180 to 450 degrees = 270 degree range, starting from left)
    const radius = 85;
    const centerX = 100;
    const centerY = 100;
    const startAngleDeg = 180;
    const endAngleDeg = 450;
    const currentAngleDeg = startAngleDeg + (currentPercent * 270);
    const targetAngleDeg = startAngleDeg + (targetPercent * 270);

    const backgroundArc = describeArc(centerX, centerY, radius, startAngleDeg, endAngleDeg);
    const currentArc = describeArc(centerX, centerY, radius, startAngleDeg, currentAngleDeg);
    const targetArc = describeArc(centerX, centerY, radius, startAngleDeg, targetAngleDeg);

    // Calculate handle positions
    const currentPos = polarToCartesian(centerX, centerY, radius, currentAngleDeg);
    const targetPos = polarToCartesian(centerX, centerY, radius, targetAngleDeg);

    this.content.innerHTML = `
      <style>
        .card-content {
          padding: 16px;
        }
        .status-bar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px;
          background: ${statusColor}1a;
          border-radius: 12px;
          margin-bottom: 16px;
        }
        .status-badge {
          display: flex;
          align-items: center;
          gap: 8px;
          color: ${statusColor};
          font-weight: 500;
          font-size: 14px;
        }
        .window-indicator {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 6px 12px;
          border-radius: 16px;
          background: ${windowOpen ? '#f44336' : '#4caf50'}20;
          color: ${windowOpen ? '#f44336' : '#4caf50'};
          font-size: 12px;
          font-weight: 500;
        }
        .slider-container {
          display: flex;
          justify-content: center;
          align-items: center;
          margin: 20px 0;
          position: relative;
        }
        .circular-slider {
          position: relative;
          width: 280px;
          height: 280px;
          cursor: pointer;
          user-select: none;
        }
        .slider-svg {
          width: 100%;
          height: 100%;
          transform: rotate(0deg);
        }
        .arc-background {
          fill: none;
          stroke: var(--divider-color);
          stroke-width: 16;
          stroke-linecap: round;
          opacity: 0.2;
        }
        .arc-current {
          fill: none;
          stroke: ${statusColor};
          stroke-width: 14;
          stroke-linecap: round;
          opacity: 0.5;
        }
        .arc-target {
          fill: none;
          stroke: ${statusColor};
          stroke-width: 16;
          stroke-linecap: round;
        }
        .current-indicator {
          fill: ${statusColor};
          stroke: white;
          stroke-width: 3;
          filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5));
          pointer-events: none;
        }
        .target-handle {
          fill: var(--primary-color);
          stroke: white;
          stroke-width: 3;
          cursor: grab;
          filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));
        }
        .target-handle:active {
          cursor: grabbing;
        }
        .slider-center {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          text-align: center;
          pointer-events: none;
          width: 70%;
        }
        .center-icons {
          display: flex;
          justify-content: center;
          gap: 20px;
          margin-bottom: 8px;
          opacity: 0.7;
        }
        .center-icons ha-icon {
          width: 24px;
          height: 24px;
        }
        .current-temp {
          font-size: 56px;
          font-weight: 300;
          color: var(--primary-text-color);
          line-height: 1;
          margin-bottom: 8px;
        }
        .temp-unit {
          font-size: 20px;
          color: var(--secondary-text-color);
          margin-left: 2px;
        }
        .separator-line {
          width: 80%;
          height: 1px;
          background: var(--divider-color);
          margin: 12px auto;
        }
        .status-info {
          display: flex;
          justify-content: center;
          align-items: center;
          gap: 16px;
          margin-top: 8px;
        }
        .status-item {
          display: flex;
          align-items: baseline;
          gap: 2px;
        }
        .status-value {
          font-size: 18px;
          font-weight: 400;
          color: var(--primary-text-color);
        }
        .status-unit {
          font-size: 12px;
          color: var(--secondary-text-color);
        }
        .status-icon {
          width: 20px;
          height: 20px;
        }
        .temp-controls {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 24px;
          margin: 20px 0;
        }
        .temp-btn {
          width: 48px;
          height: 48px;
          border-radius: 50%;
          border: 2px solid var(--primary-color);
          background: var(--card-background-color);
          color: var(--primary-color);
          font-size: 28px;
          font-weight: 300;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
          line-height: 1;
        }
        .temp-btn:hover {
          background: var(--primary-color);
          color: white;
          transform: scale(1.05);
        }
        .temp-btn:active {
          transform: scale(0.95);
        }
        .target-temp-control {
          font-size: 32px;
          font-weight: 300;
          min-width: 100px;
          text-align: center;
          color: var(--primary-text-color);
        }
        .temp-range {
          text-align: center;
          font-size: 13px;
          color: var(--secondary-text-color);
          margin-top: 12px;
          opacity: 0.7;
        }
        .sensors-info {
          display: flex;
          gap: 12px;
          margin: 16px 0;
          font-size: 12px;
          color: var(--secondary-text-color);
          justify-content: center;
        }
        .sensor-item {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .trv-list {
          margin-top: 20px;
        }
        .trv-item {
          background: var(--secondary-background-color);
          border-radius: 12px;
          padding: 16px;
          margin-bottom: 12px;
          transition: all 0.2s;
        }
        .trv-item:hover {
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .trv-name {
          font-weight: 500;
          margin-bottom: 12px;
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 15px;
        }
        .trv-stats {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
          margin-bottom: 12px;
        }
        .stat {
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .stat-label {
          font-size: 11px;
          color: var(--secondary-text-color);
          opacity: 0.8;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .stat-value {
          font-size: 15px;
          font-weight: 500;
        }
        .validation-indicator {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          margin-left: 6px;
        }
        .validation-icon {
          width: 14px;
          height: 14px;
        }
        .validation-valid {
          color: #4caf50;
        }
        .validation-invalid {
          color: #f44336;
        }
        .validation-details {
          font-size: 10px;
          color: var(--secondary-text-color);
          margin-top: 2px;
          opacity: 0.8;
        }
        .validation-mismatch {
          color: #ff9800;
          font-weight: 500;
        }
        .valve-bar {
          margin-top: 12px;
        }
        .valve-bar-bg {
          background: var(--divider-color);
          border-radius: 6px;
          height: 8px;
          overflow: hidden;
        }
        .valve-bar-fill {
          background: linear-gradient(90deg, ${statusColor}, ${statusColor}dd);
          height: 100%;
          transition: width 0.3s ease;
          border-radius: 6px;
        }
        .valve-label {
          display: flex;
          justify-content: space-between;
          font-size: 11px;
          color: var(--secondary-text-color);
          margin-top: 6px;
        }
        .status-reason {
          margin-top: 12px;
          padding: 10px;
          background: var(--card-background-color);
          border-radius: 8px;
          font-size: 12px;
          color: var(--secondary-text-color);
          border-left: 3px solid ${statusColor};
        }
        .not-found {
          color: var(--error-color);
          padding: 16px;
          text-align: center;
        }
        .performance-section {
          margin-top: 24px;
          background: var(--secondary-background-color);
          border-radius: 12px;
          padding: 16px;
        }
        .performance-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 16px;
          font-weight: 500;
          font-size: 15px;
        }
        .performance-score {
          display: flex;
          justify-content: center;
          align-items: center;
          margin-bottom: 20px;
        }
        .score-circle {
          position: relative;
          width: 80px;
          height: 80px;
          display: flex;
          align-items: center;
          justify-content: center;
          background: conic-gradient(from 0deg, ${statusColor}40 0deg, ${statusColor} var(--score-angle, 0deg), var(--divider-color) var(--score-angle, 0deg) 360deg);
          border-radius: 50%;
          margin: 0 20px;
        }
        .score-inner {
          position: absolute;
          width: 60px;
          height: 60px;
          background: var(--card-background-color);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-direction: column;
        }
        .score-value {
          font-size: 16px;
          font-weight: 600;
          color: ${statusColor};
        }
        .score-unit {
          font-size: 10px;
          color: var(--secondary-text-color);
        }
        .performance-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px;
          margin-bottom: 16px;
        }
        .perf-stat {
          display: flex;
          flex-direction: column;
          gap: 4px;
          padding: 12px;
          background: var(--card-background-color);
          border-radius: 8px;
        }
        .perf-stat-label {
          font-size: 10px;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .perf-stat-value {
          font-size: 14px;
          font-weight: 500;
          color: var(--primary-text-color);
        }
        .night-saving-indicator {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 12px;
          background: ${nightSavingActive ? '#4caf50' : 'var(--divider-color)'}20;
          color: ${nightSavingActive ? '#4caf50' : 'var(--secondary-text-color)'};
          border-radius: 16px;
          font-size: 12px;
          font-weight: 500;
          justify-content: center;
        }
        ha-icon {
          width: 20px;
          height: 20px;
        }
      </style>

      <div class="status-bar">
        <div class="status-badge">
          <ha-icon icon="${statusIcon}"></ha-icon>
          ${heatingStatus.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
        </div>
        ${attrs.window_sensor ? `
          <div class="window-indicator">
            <ha-icon icon="mdi:window-${windowOpen ? 'open' : 'closed'}-variant"></ha-icon>
            ${windowOpen ? 'Open' : 'Closed'}
          </div>
        ` : ''}
      </div>

      <div class="slider-container">
        <svg class="slider-svg" viewBox="0 0 200 200" id="slider-svg">
          <!-- Background arc -->
          <path
            class="arc-background"
            d="${backgroundArc}"
          />

          <!-- Target temperature arc (interactive area) -->
          <path
            class="arc-target"
            d="${targetArc}"
            id="target-arc"
          />

          <!-- Current temperature arc -->
          <path
            class="arc-current"
            d="${currentArc}"
          />

          <!-- Current temperature indicator dot -->
          <circle
            class="current-indicator"
            cx="${currentPos.x}"
            cy="${currentPos.y}"
            r="10"
          />

          <!-- Draggable handle -->
          <circle
            class="target-handle"
            cx="${targetPos.x}"
            cy="${targetPos.y}"
            r="10"
            id="temp-handle"
          />
        </svg>

        <div class="slider-center">
          <div class="center-icons">
            <ha-icon icon="${statusIcon}" style="color: ${statusColor}"></ha-icon>
          </div>
          <div class="current-temp">
            ${currentTemp.toFixed(1)}<span class="temp-unit">°C</span>
          </div>
          <div class="separator-line"></div>
          <div class="status-info">
            <div class="status-item">
              <span class="status-value">${targetTemp.toFixed(1)}</span>
              <span class="status-unit">°C</span>
            </div>
            <ha-icon icon="${statusIcon}" class="status-icon" style="color: ${statusColor}"></ha-icon>
          </div>
        </div>
      </div>

      <div class="temp-controls">
        <button class="temp-btn" id="temp-down">−</button>
          <div class="target-temp-control">${nightSavingActive && adjustedTargetTemp ? adjustedTargetTemp.toFixed(1) : targetTemp}°C</div>
          <button class="temp-btn" id="temp-up">+</button>
        </div>

        ${nightSavingActive ? `
        <div class="temp-range" style="color: #4caf50; font-weight: 500;">
          Night saving: ${targetTemp}°C → ${adjustedTargetTemp ? adjustedTargetTemp.toFixed(1) : targetTemp}°C
        </div>
        ` : `
        <div class="temp-range">${minTemp}°C - ${maxTemp}°C (Step: ${step}°C)</div>
        `}
        <div class="sensor-item">
          <ha-icon icon="mdi:thermometer"></ha-icon>
          ${attrs.temp_sensor || 'N/A'}
        </div>
      </div>

      <div class="trv-list">
        ${trvs.map(trv => `
          <div class="trv-item">
            <div class="trv-name">
              <ha-icon icon="mdi:radiator"></ha-icon>
              ${trv.name}
            </div>

            <div class="trv-stats">
              <div class="stat">
                <div class="stat-label">Return Temp</div>
                <div class="stat-value" style="color: ${trv.returnTemp && trv.closeThreshold && trv.returnTemp >= trv.closeThreshold ? '#f44336' : 'inherit'}">${trv.returnTemp !== undefined ? trv.returnTemp.toFixed(1) : 'N/A'}°C</div>
              </div>
              <div class="stat">
                <div class="stat-label">Valve Position</div>
                <div class="stat-value">
                  ${trv.valvePosition !== undefined ? trv.valvePosition : 'N/A'}%
                  <span class="validation-indicator">
                    <ha-icon 
                      icon="mdi:${trv.valvePositionValid ? 'check-circle' : 'alert-circle'}" 
                      class="validation-icon ${trv.valvePositionValid ? 'validation-valid' : 'validation-invalid'}"
                    ></ha-icon>
                  </span>
                </div>
                ${trv.actualValvePosition !== null ? `
                <div class="validation-details">
                  TRV: ${trv.actualValvePosition}% ${!trv.valvePositionValid ? `<span class="validation-mismatch">(Expected: ${trv.valvePosition}%)</span>` : ''}
                </div>
                ` : ''}
              </div>
              <div class="stat">
                <div class="stat-label">Target Temp</div>
                <div class="stat-value">
                  ${trv.expectedSetpoint ? trv.expectedSetpoint.toFixed(1) : 'N/A'}°C
                  <span class="validation-indicator">
                    <ha-icon 
                      icon="mdi:${trv.setpointValid ? 'check-circle' : 'alert-circle'}" 
                      class="validation-icon ${trv.setpointValid ? 'validation-valid' : 'validation-invalid'}"
                    ></ha-icon>
                  </span>
                </div>
                ${trv.actualSetpoint !== null ? `
                <div class="validation-details">
                  TRV: ${trv.actualSetpoint.toFixed(1)}°C ${!trv.setpointValid ? `<span class="validation-mismatch">(Expected: ${trv.expectedSetpoint.toFixed(1)}°C)</span>` : ''}
                </div>
                ` : ''}
              </div>
              <div class="stat">
                <div class="stat-label">Status</div>
                <div class="stat-value" style="font-size: 12px; color: ${trv.status === 'healthy' ? '#4caf50' : trv.status === 'control_disabled' ? '#9e9e9e' : '#ff9800'}">${trv.status || 'Unknown'}</div>
              </div>
            </div>

            <div class="valve-bar">
              <div class="valve-bar-bg">
                <div class="valve-bar-fill" style="width: ${trv.actualValvePosition || trv.valvePosition || 0}%"></div>
                ${trv.actualValvePosition !== trv.valvePosition && trv.actualValvePosition !== null && trv.valvePosition !== null ? `
                <div class="valve-bar-expected" style="
                  position: absolute; 
                  top: 0; 
                  left: ${trv.valvePosition}%; 
                  width: 2px; 
                  height: 100%; 
                  background: #ff9800; 
                  opacity: 0.8;
                "></div>
                ` : ''}
              </div>
              <div class="valve-label">
                <span>Valve: ${trv.actualValvePosition !== null ? trv.actualValvePosition : trv.valvePosition || 0}%${trv.actualValvePosition !== trv.valvePosition && trv.actualValvePosition !== null && trv.valvePosition !== null ? ` (Expected: ${trv.valvePosition}%)` : ''}</span>
                <span>Max: ${trv.maxPosition || 100}%</span>
              </div>
            </div>

            ${trv.statusReason ? `
              <div class="status-reason">
                ${trv.statusReason}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>

      ${performanceScore !== undefined ? `
      <div class="performance-section">
        <div class="performance-header">
          <ha-icon icon="mdi:speedometer"></ha-icon>
          Performance Monitoring
        </div>

        <div class="performance-score">
          <div class="score-circle" style="--score-angle: ${(performanceScore || 0) * 3.6}deg;">
            <div class="score-inner">
              <div class="score-value">${(performanceScore || 0).toFixed(0)}</div>
              <div class="score-unit">%</div>
            </div>
          </div>
        </div>

        <div class="performance-grid">
          <div class="perf-stat">
            <div class="perf-stat-label">Temperature Accuracy</div>
            <div class="perf-stat-value">${tempAccuracy || 'N/A'}</div>
          </div>
          <div class="perf-stat">
            <div class="perf-stat-label">Control Stability</div>
            <div class="perf-stat-value">${controlStability || 'N/A'}</div>
          </div>
          <div class="perf-stat">
            <div class="perf-stat-label">Runtime Hours</div>
            <div class="perf-stat-value">${runtimeHours ? runtimeHours.toFixed(1) : 'N/A'}h</div>
          </div>
          <div class="perf-stat">
            <div class="perf-stat-label">Actions/Hour</div>
            <div class="perf-stat-value">${actionsPerHour || 'N/A'}</div>
          </div>
          <div class="perf-stat">
            <div class="perf-stat-label">Max Deviation</div>
            <div class="perf-stat-value">${maxTempDev || 'N/A'}</div>
          </div>
          <div class="perf-stat">
            <div class="perf-stat-label">Total Actions</div>
            <div class="perf-stat-value">${totalActions || 0}</div>
          </div>
        </div>

        ${nightSavingActive ? `
        <div class="night-saving-indicator">
          <ha-icon icon="mdi:weather-night"></ha-icon>
          Night Saving Active${adjustedTargetTemp ? ` (${adjustedTargetTemp.toFixed(1)}°C)` : ''}
        </div>
        ` : ''}

        ${nightSavingUses > 0 || windowEvents > 0 ? `
        <div class="performance-grid" style="margin-top: 12px; grid-template-columns: 1fr 1fr;">
          ${nightSavingUses > 0 ? `
          <div class="perf-stat">
            <div class="perf-stat-label">Night Saving Uses</div>
            <div class="perf-stat-value">${nightSavingUses}</div>
          </div>
          ` : ''}
          ${windowEvents > 0 ? `
          <div class="perf-stat">
            <div class="perf-stat-label">Window Events</div>
            <div class="perf-stat-value">${windowEvents}</div>
          </div>
          ` : ''}
        </div>
        ` : ''}
      </div>
      ` : ''}
    `;

    // Add event listeners for temperature control
    const tempUpBtn = this.content.querySelector('#temp-up');
    const tempDownBtn = this.content.querySelector('#temp-down');
    const handle = this.content.querySelector('#temp-handle');
    const slider = this.content.querySelector('#slider-svg');

    if (tempUpBtn) {
      tempUpBtn.addEventListener('click', () => {
        const newTemp = Math.min(maxTemp, targetTemp + step);
        this.setTemperature(entityId, newTemp);
      });
    }

    if (tempDownBtn) {
      tempDownBtn.addEventListener('click', () => {
        const newTemp = Math.max(minTemp, targetTemp - step);
        this.setTemperature(entityId, newTemp);
      });
    }

    // Drag functionality for circular slider
    const updateTemperatureFromAngle = (angle) => {
      // Normalize angle to 0-270 range (starting from left)
      let normalizedAngle = ((angle - 180 + 360) % 360);
      if (normalizedAngle > 270) return; // Out of valid range

      const percent = normalizedAngle / 270;
      let newTemp = minTemp + (percent * tempRange);

      // Round to step
      newTemp = Math.round(newTemp / step) * step;
      newTemp = Math.max(minTemp, Math.min(maxTemp, newTemp));

      this.setTemperature(entityId, newTemp);
    };

    const getAngleFromEvent = (event) => {
      const rect = slider.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      let clientX, clientY;
      if (event.type.startsWith('touch')) {
        const touch = event.touches[0] || event.changedTouches[0];
        clientX = touch.clientX;
        clientY = touch.clientY;
      } else {
        clientX = event.clientX;
        clientY = event.clientY;
      }

      const x = clientX - centerX;
      const y = clientY - centerY;
      let angle = Math.atan2(y, x) * (180 / Math.PI) + 90;
      if (angle < 0) angle += 360;

      return angle;
    };

    const startDrag = (event) => {
      this._isDragging = true;
      event.preventDefault();
    };

    const drag = (event) => {
      if (!this._isDragging) return;
      event.preventDefault();

      const angle = getAngleFromEvent(event);
      updateTemperatureFromAngle(angle);
    };

    const endDrag = () => {
      this._isDragging = false;
    };

    if (handle && slider) {
      // Mouse events
      handle.addEventListener('mousedown', startDrag);
      document.addEventListener('mousemove', drag);
      document.addEventListener('mouseup', endDrag);

      // Touch events
      handle.addEventListener('touchstart', startDrag, { passive: false });
      document.addEventListener('touchmove', drag, { passive: false });
      document.addEventListener('touchend', endDrag);

      // Click on arc to set temperature
      slider.addEventListener('click', (event) => {
        if (!this._isDragging) {
          const angle = getAngleFromEvent(event);
          updateTemperatureFromAngle(angle);
        }
      });
    }
  }

  setTemperature(entityId, temperature) {
    this._hass.callService('climate', 'set_temperature', {
      entity_id: entityId,
      temperature: temperature
    });
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('You need to define an entity');
    }
    this.config = config;
  }

  static getConfigElement() {
    return document.createElement('trv-control-card-editor');
  }

  static getStubConfig() {
    return {
      entity: '',
      name: ''
    };
  }

  getCardSize() {
    return 3;
  }
}

console.log('TRV Control Card: Main class defined');
customElements.define('trv-control-card', TRVControlCard);
console.log('TRV Control Card: Custom element registered');

// Visual Editor for Lovelace UI Configuration
class TRVControlCardEditor extends HTMLElement {
  constructor() {
    super();
    console.log('TRV Control Card Editor: Constructor called');
  }

  setConfig(config) {
    console.log('TRV Control Card Editor: setConfig called with', config);
    this._config = { ...config };
    this.render();
  }

  render() {
    console.log('TRV Control Card Editor: render called');
    try {
      this.innerHTML = `
        <style>
          :host {
            display: block;
            min-height: 200px;
          }
          .card-config {
            padding: 24px;
            background: var(--card-background-color);
          }
          .input-group {
            margin-bottom: 20px;
          }
          .input-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            font-size: 14px;
            color: var(--primary-text-color);
          }
          .input-group input {
            width: 100%;
            padding: 12px;
            border: 1px solid var(--divider-color);
            border-radius: 4px;
            background: var(--card-background-color);
            color: var(--primary-text-color);
            font-size: 16px;
            box-sizing: border-box;
            font-family: inherit;
          }
          .input-group input:focus {
            outline: none;
            border-color: var(--primary-color);
            box-shadow: 0 0 0 1px var(--primary-color);
          }
          .hint {
            font-size: 12px;
            color: var(--secondary-text-color);
            margin-top: 6px;
            font-style: italic;
          }
        </style>
        <div class="card-config">
          <div class="input-group">
            <label for="entity">Entity *</label>
            <input
              type="text"
              id="entity"
              placeholder="climate.bedroom_trv"
              value="${this._config.entity || ''}"
            />
            <div class="hint">Climate entity ID (required)</div>
          </div>
          <div class="input-group">
            <label for="name">Name</label>
            <input
              type="text"
              id="name"
              placeholder="Bedroom TRV"
              value="${this._config.name || ''}"
            />
            <div class="hint">Display name (optional)</div>
          </div>
        </div>
      `;

      const entityInput = this.querySelector('#entity');
      const nameInput = this.querySelector('#name');

      if (entityInput) {
        entityInput.addEventListener('input', (e) => {
          this._config.entity = e.target.value;
          this._fireConfigChanged();
        });
      }

      if (nameInput) {
        nameInput.addEventListener('input', (e) => {
          this._config.name = e.target.value;
          this._fireConfigChanged();
        });
      }

      console.log('TRV Control Card Editor: render complete');
    } catch (error) {
      console.error('TRV Control Card Editor: render error', error);
    }
  }

  _fireConfigChanged() {
    const event = new CustomEvent('config-changed', {
      detail: { config: this._config },
      bubbles: true,
      composed: true
    });
    this.dispatchEvent(event);
  }

  set hass(hass) {
    this._hass = hass;
  }

  get hass() {
    return this._hass;
  }
}

customElements.define('trv-control-card-editor', TRVControlCardEditor);

// Register the card with Home Assistant
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'trv-control-card',
  name: 'TRV Control Card',
  description: 'Advanced TRV Control integration card with visual editor',
  preview: false,
  documentationURL: 'https://github.com/yourusername/trv_control'
});

console.log('TRV Control Card: Registered successfully with Home Assistant');
console.log('TRV Control Card: Available as type "trv-control-card"');
