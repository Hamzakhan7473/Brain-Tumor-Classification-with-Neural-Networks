import React from "react";
import { Link } from "react-router-dom";

export type DashboardInsight = {
  id: string;
  title: string;
  description: string;
  to: string;
  cta: string;
  tone?: "default" | "action" | "muted";
};

type DashboardInsightsProps = {
  insights: DashboardInsight[];
  loading?: boolean;
};

export function DashboardInsights({ insights, loading }: DashboardInsightsProps): React.ReactElement {
  if (loading) {
    return (
      <div className="dashboard-insights">
        {[0, 1, 2].map((i) => (
          <div key={i} className="dashboard-insight dashboard-insight--skeleton">
            <div className="ui-skeleton ui-skeleton--title" />
            <div className="ui-skeleton ui-skeleton--line" />
            <div className="ui-skeleton ui-skeleton--btn" />
          </div>
        ))}
      </div>
    );
  }

  if (!insights.length) return <div className="dashboard-insights" />;

  return (
    <div className="dashboard-insights">
      {insights.map((item) => (
        <article
          key={item.id}
          className={`dashboard-insight${item.tone === "action" ? " dashboard-insight--action" : ""}${
            item.tone === "muted" ? " dashboard-insight--muted" : ""
          }`}
        >
          <div>
            <h3 className="dashboard-insight-title">{item.title}</h3>
            <p className="dashboard-insight-desc">{item.description}</p>
          </div>
          <Link to={item.to} className="dashboard-insight-cta">
            {item.cta}
          </Link>
        </article>
      ))}
    </div>
  );
}
