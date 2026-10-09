import { useApp } from "../state/AppProvider";
import { downloadJson } from "../shared/format";

export function DataPage() {
  const { state } = useApp();
  const dataset = state.dataset?.dataset;
  const result = state.optimized ?? state.evaluated;
  if (!dataset) return <p>Данные ещё загружаются.</p>;
  return (
    <section>
      <h2 className="page-title">Данные и модель</h2>
      <p className="lede">{dataset.metadata.disclaimer}</p>
      <article className="card" style={{ marginBottom: 16 }}>
        <h2>Происхождение</h2>
        {dataset.provenance.map((card) => (
          <div key={card.id} style={{ marginBottom: 12 }}>
            <strong>{card.title}</strong>
            <div className="hint">{card.kind} · {card.note}</div>
          </div>
        ))}
      </article>
      <article className="card" style={{ marginBottom: 16 }}>
        <h2>Допущения</h2>
        <ul>
          <li>Компания в модели — перевозчик / 3PL. Выручка — плата за перевозку, не стоимость товара.</li>
          <li>Один горизонт: условная смена {dataset.metadata.horizon_min} минут. Это учебный параметр, не норма режима труда.</li>
          <li>Один неделимый заказ в кузове. Цепочка — последовательные заказы без лишнего возврата на базу.</li>
          <li>Фиксированная зарплата и владение парком не исчезают, если машина проехала меньше.</li>
          <li>Тариф подрядчика all-in: своё топливо на него не начисляется.</li>
          <li>Нет сертифицированной грузовой маршрутизации и покрытия СТО.</li>
        </ul>
      </article>
      <article className="card">
        <h2>Метод и воспроизводимость</h2>
        <p>Перебор допустимых цепочек до 3 заказов и дискретный выбор. Нейросеть не обучается.</p>
        {state.optimized && (
          <>
            <p>Движок: {state.optimized.solver.engine}. Статус: {state.optimized.solver.solver_status}. Качество: {state.optimized.solver.solution_quality}.</p>
            <p className="hint">{state.optimized.solver.note}</p>
            <p className="hint">Кандидатов: {state.optimized.solver.candidate_count}. Поиск: {state.optimized.solver.elapsed_ms} мс. Проверок плана: {state.optimized.baseline.validation.checks.length}.</p>
          </>
        )}
        {result && (
          <p className="hint">
            dataset {result.computation.dataset_version} · hash {result.dataset_hash.slice(0, 12)} · engine {result.computation.engine_version} · сценарий {result.scenario_hash.slice(0, 12)} · расчёт {result.computation.elapsed_ms} мс
          </p>
        )}
        <div className="actions">
          <button className="btn" disabled={!state.draft} onClick={() => state.draft && downloadJson("scenario-input.json", { ...state.draft, dataset_hash: state.dataset?.dataset_hash })}>Сохранить вход</button>
          <button className="btn" disabled={!result} onClick={() => result && downloadJson("scenario-result.json", result)}>Сохранить результат</button>
        </div>
      </article>
    </section>
  );
}
