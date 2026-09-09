import React from "react";

export function DashboardTableSkeleton(): React.ReactElement {
  return (
    <div className="dashboard-table-wrap dashboard-table-wrap--loading">
      <div className="dashboard-skeleton-rows">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="dashboard-skeleton-row">
            <div className="ui-skeleton ui-skeleton--cell" style={{ flex: 2 }} />
            <div className="ui-skeleton ui-skeleton--cell" />
            <div className="ui-skeleton ui-skeleton--cell" />
            <div className="ui-skeleton ui-skeleton--cell" />
          </div>
        ))}
      </div>
    </div>
  );
}
