class TRVControlCard extends HTMLElement {
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

    // Get all TRV data
    const trvs = [];
    for (let key in attrs) {
      if (key.endsWith('_entity') && !key.startsWith('temp_sensor') && !key.startsWith('window_sensor')) {
        const trvPrefix = key.replace('_entity', '');
        trvs.push({
          name: trvPrefix.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
          entity: attrs[key],
          returnTemp: attrs[`${trvPrefix}_return_temp`],
          returnSensor: attrs[`${trvPrefix}_return_temp_sensor`],
          valvePosition: attrs[`${trvPrefix}_valve_position`],
          valveActive: attrs[`${trvPrefix}_valve_control_active`],
          closeThreshold: attrs[`${trvPrefix}_close_threshold`],
          openThreshold: attrs[`${trvPrefix}_open_threshold`],
          maxPosition: attrs[`${trvPrefix}_max_position`],
          status: attrs[`${trvPrefix}_status`],
          statusReason: attrs[`${trvPrefix}_status_reason`]
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
    
    // Calculate gauge parameters
    const tempRange = maxTemp - minTemp;
    const currentAngle = ((currentTemp - minTemp) / tempRange) * 270 - 135;
    const targetAngle = ((targetTemp - minTemp) / tempRange) * 270 - 135;

    this.content.innerHTML = `
      <style>
        .gauge-container {
          display: flex;
          justify-content: center;
          align-items: center;
          margin: 20px 0;
          position: relative;
        }
        .gauge {
          width: 200px;
          height: 200px;
          position: relative;
        }
        .gauge-circle {
          width: 100%;
          height: 100%;
          border-radius: 50%;
          background: conic-gradient(
            from -135deg,
            ${statusColor}20 0deg,
            ${statusColor}20 ${(currentTemp - minTemp) / tempRange * 270}deg,
            var(--divider-color) ${(currentTemp - minTemp) / tempRange * 270}deg,
            var(--divider-color) 270deg,
            transparent 270deg
          );
          position: relative;
        }
        .gauge-inner {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          width: 160px;
          height: 160px;
          border-radius: 50%;
          background: var(--card-background-color);
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
        }
        .current-temp {
          font-size: 36px;
          font-weight: bold;
          color: ${statusColor};
        }
        .temp-unit {
          font-size: 16px;
          color: var(--secondary-text-color);
          margin-top: -8px;
        }
        .target-temp-display {
          font-size: 14px;
          color: var(--secondary-text-color);
          margin-top: 4px;
        }
        .temp-controls {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 16px;
          margin: 16px 0;
        }
        .temp-btn {
          width: 40px;
          height: 40px;
          border-radius: 50%;
          border: 2px solid var(--primary-color);
          background: var(--card-background-color);
          color: var(--primary-color);
          font-size: 24px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.2s;
        }
        .temp-btn:hover {
          background: var(--primary-color);
          color: white;
        }
        .temp-btn:active {
          transform: scale(0.95);
        }
        .target-temp-control {
          font-size: 28px;
          font-weight: bold;
          min-width: 80px;
          text-align: center;
        }
        .status-bar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 12px;
          background: ${statusColor}10;
          border-radius: 8px;
          margin-bottom: 16px;
        }
        .status-badge {
          display: flex;
          align-items: center;
          gap: 8px;
          color: ${statusColor};
          font-weight: 500;
        }
        .window-indicator {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 8px;
          border-radius: 8px;
          background: ${windowOpen ? '#f44336' : '#4caf50'}20;
          color: ${windowOpen ? '#f44336' : '#4caf50'};
          font-size: 12px;
        }
        .sensors-info {
          display: flex;
          gap: 12px;
          margin: 12px 0;
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
          margin-top: 16px;
        }
        .trv-item {
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 8px;
          padding: 12px;
          margin-bottom: 12px;
        }
        .trv-name {
          font-weight: 500;
          margin-bottom: 8px;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .trv-stats {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 8px;
          margin-bottom: 8px;
        }
        .stat {
          display: flex;
          flex-direction: column;
        }
        .stat-label {
          font-size: 11px;
          color: var(--secondary-text-color);
        }
        .stat-value {
          font-size: 14px;
          font-weight: 500;
        }
        .valve-bar {
          margin-top: 8px;
        }
        .valve-bar-bg {
          background: var(--divider-color);
          border-radius: 4px;
          height: 8px;
          overflow: hidden;
        }
        .valve-bar-fill {
          background: ${statusColor};
          height: 100%;
          transition: width 0.3s ease;
        }
        .valve-label {
          display: flex;
          justify-content: space-between;
          font-size: 11px;
          color: var(--secondary-text-color);
          margin-top: 4px;
        }
        .status-reason {
          margin-top: 8px;
          padding: 8px;
          background: var(--secondary-background-color);
          border-radius: 4px;
          font-size: 12px;
          color: var(--secondary-text-color);
        }
        .not-found {
          color: var(--error-color);
          padding: 16px;
        }
        ha-icon {
          width: 18px;
          height: 18px;
        }
        .temp-range {
          text-align: center;
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-top: 8px;
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

      <div class="gauge-container">
        <div class="gauge">
          <div class="gauge-circle">
            <div class="gauge-inner">
              <div class="current-temp">${currentTemp.toFixed(1)}</div>
              <div class="temp-unit">°C</div>
              <div class="target-temp-display">Target: ${targetTemp}°C</div>
            </div>
          </div>
        </div>
      </div>

      <div class="temp-controls">
        <button class="temp-btn" id="temp-down">−</button>
        <div class="target-temp-control">${targetTemp}°C</div>
        <button class="temp-btn" id="temp-up">+</button>
      </div>
      
      <div class="temp-range">${minTemp}°C - ${maxTemp}°C</div>

      <div class="sensors-info">
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
                <div class="stat-value">${trv.returnTemp !== undefined ? trv.returnTemp.toFixed(1) : 'N/A'}°C</div>
              </div>
              <div class="stat">
                <div class="stat-label">Valve Position</div>
                <div class="stat-value">${trv.valvePosition !== undefined ? trv.valvePosition : 'N/A'}%</div>
              </div>
              <div class="stat">
                <div class="stat-label">Close Threshold</div>
                <div class="stat-value">${trv.closeThreshold !== undefined ? trv.closeThreshold : 'N/A'}°C</div>
              </div>
              <div class="stat">
                <div class="stat-label">Open Threshold</div>
                <div class="stat-value">${trv.openThreshold !== undefined ? trv.openThreshold : 'N/A'}°C</div>
              </div>
            </div>

            <div class="valve-bar">
              <div class="valve-bar-bg">
                <div class="valve-bar-fill" style="width: ${trv.valvePosition || 0}%"></div>
              </div>
              <div class="valve-label">
                <span>Valve: ${trv.valvePosition || 0}%</span>
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
    `;
    
    // Add event listeners for temperature control
    const tempUpBtn = this.content.querySelector('#temp-up');
    const tempDownBtn = this.content.querySelector('#temp-down');
    
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

  getCardSize() {
    return 3;
  }
}

customElements.define('trv-control-card', TRVControlCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'trv-control-card',
  name: 'TRV Control Card',
  description: 'Display TRV Control integration information'
});
