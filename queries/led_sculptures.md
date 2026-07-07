LED-скульптуры, световые эффекты, схемы управления светодиодами и реиспользование компонентов.

Интересует:
- LED-паттерны: мигание, fading, бегущие огни, дыхание, PWM, программируемые световые эффекты
  - wave/ripple, stochastic/chaotic blinking, cellular automata
  - LED-гирлянды и их вариации
  - chaser circuits (4017 decade counter, shift register cascading)
  - техники "breathing" — экспоненциальные кривые, sine-wave modulation, плавное нарастание/спад яркости
  - RC-фильтры для smooth fading
  - state machine-driven LED sequencing, таймерные/прерывания/DMA подходы
- Дискретная аналоговая схемотехника для LED: транзисторные генераторы (astable multivibrator), 555 timer, op-amp relaxation oscillator, CMOS 4000-series, UJT/PUT relaxation oscillator, CD4017 LED chaser, линейные регуляторы тока, схемы без микроконтроллеров
- Схемотехника для LED на микроконтроллерах
- Маломощные схемы: coin cell (CR2032, LiR2450), boost converter, low-power MCU — чтобы объект работал от батарейки
- Реиспользование электронных компонентов из старой техники:
  - LED salvaging: извлечение LED из старой техники, определение Vf/If без даташита
  - Reuse LED drivers из LCD-подсветок, мониторов, принтеров
  - E-waste harvesting: детали для LED-схем (трансформаторы, конденсаторы, транзисторы)
  - Power supply repurposing: ATX/laptop PSU → bench supply для LED-проектов
  - Recycled components в LED art: CD/DVD sleds, hard drive magnets, VFD displays
  - Использование старых devboard (STM32, ESP) как LED-контроллеров
- Технически ценные комментарии: альтернативные компоненты, схемы, исправления ошибок автора

Не интересует:
- Чисто декоративные проекты без схемотехники или кода
- Крупные инсталляции без применимости к настольному масштабу
- Статьи только про 3D-печать/корпус без электроники
